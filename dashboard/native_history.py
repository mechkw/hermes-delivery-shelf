"""Read-only native history adapter vendored from Bookmarks 3f70841.

Plugin-owned schema seam, NOT a public ctx source API. No SessionDB construction,
migration, index materialization, tools, or persistence. Kept separate so a future
supported bounded native artifact/history API can replace it. See SOURCE-ADAPTER.md.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import stat
import time
from fastapi import HTTPException

SOURCE_SESSION_WINDOW = 1000
SOURCE_RESPONSE_WINDOW = 500
SOURCE_CONTENT_BYTES = 16384
SOURCE_PREVIEW_CHARS = 350
SESSION_ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"

# Mirror THINK_TAG_NAMES in agent/think_scrubber.py and the tool/function/arg
# carriers in agent/agent_runtime_helpers.py, plus analysis/tool_use. Keep this
# adapter independent of the host's heavyweight runtime-helper imports.
SOURCE_PRIVATE_TAG_NAMES = (
    "think", "thinking", "reasoning", "thought", "REASONING_SCRATCHPAD",
    "思考", "反思", "推理", "推敲", "analysis", "tool_use",
    "tool_call", "tool_calls", "tool_result", "function_call", "function_calls",
    "function", "arg_key", "arg_value",
)
SOURCE_PRIVATE_TAG_RE = re.compile(
    r"<(?P<close>/?)(?P<name>(?:[\w.-]+:)?(?:" + "|".join(SOURCE_PRIVATE_TAG_NAMES)
    + r"))(?=[\s/>]|$)"
    # Quotes may contain '>'; a missing terminator is still a private carrier.
    + r'''(?P<attrs>(?:[^<>"']|"[^"]*(?:"|$)|'[^']*(?:'|$))*)(?P<end>>|(?=<)|$)''',
    re.I,
)


def source_timestamp(value):
    # SQLite can contain corrupt/non-numeric cells. Never emit NaN/Infinity or
    # mistake a millisecond timestamp for seconds (year 9999 is the upper bound).
    if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 253402300799:
        return float(value)
    return None


def source_label(value, limit):
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c for c in value if c.isprintable() or c.isspace()).split())[:limit]


def source_preview(content, *, role="assistant", limit: int | None = SOURCE_PREVIEW_CHARS, project_only=False, text_filter=None, keep_lines=False):
    """Decode the native NUL-json marker, projecting only known visible text blocks.

    Never recursively stringify unknown blocks: their text/content may be reasoning,
    tool arguments or media. Malformed/oversized payloads are not previewable.
    """
    if not isinstance(content, str):
        return ""
    if content.startswith("\x00json:"):
        try:
            content = json.loads(content[6:])
        except (ValueError, RecursionError):
            return ""
    def visible(value, depth=0):
        if depth > 8:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [text for block in value if isinstance(block, dict) for text in visible(block, depth + 1)]
        if not isinstance(value, dict) or any(value.get(k) for k in ("thought", "reasoning", "hidden", "synthetic", "model_only")) or value.get("role", role) != role:
            return []
        if value.get("channel") not in (None, "final", "commentary"):
            return []
        if value.get("type") in (("text", "output_text", "input_text") if role == 'user' else ("text", "output_text")) and isinstance(value.get("text"), str):
            return [value["text"]]
        if value.get("type") == "message" and value.get("role") == role:
            return visible(value.get("content"), depth + 1)
        return []
    blocks = visible(content)
    if text_filter is not None:
        blocks = [text_filter(block) for block in blocks]
    text = ('\n' if project_only or keep_lines else ' ').join(blocks)
    if project_only:
        # Internal generation step only: preserve carrier boundaries before
        # stripping them, then call the normal scrubber on the human projection.
        return text
    # Some providers save tagged reasoning inside content rather than in its
    # dedicated column. Only a matching closer may release a private block;
    # orphan closers invalidate the preceding prefix, unfinished tags the tail.
    parts, stack, start = [], [], 0
    for tag in SOURCE_PRIVATE_TAG_RE.finditer(text):
        if not stack:
            parts.append(text[start:tag.start()])
            if tag.group("close"):
                parts.clear()
        if not tag.group("end"):
            start = len(text)
            break
        name = tag.group("name").casefold()
        if tag.group("close"):
            if stack and stack[-1] == name:
                stack.pop()
        elif not tag.group("attrs").rstrip().endswith("/"):
            stack.append(name)
        start = tag.end()
    if not stack:
        parts.append(text[start:])
    text = re.sub(r"data:[^\s<>\"']+", "[media omitted]", " ".join(parts), flags=re.I)
    text = text if keep_lines else source_label(text, len(text))
    return text[:limit - 1] + "…" if limit is not None and len(text) > limit else text


def source_page(items, q, limit, offset, window, truncated, fields):
    needle = q.casefold().strip()
    matches = [item for item in items if not needle or any(needle in str(item[key]).casefold() for key in fields)]
    return {"items": matches[offset:offset + limit], "has_more": len(matches) > offset + limit,
            "window": {"limit": window, "truncated": truncated}}

GENERATION_ROW_LIMIT = 4000
GENERATION_MESSAGE_BYTES = 65536
GENERATION_PAYLOAD_BYTES = 262144

_SYNTHETIC = re.compile(
    r"(?:\[System:|\[CONTEXT|\[PRIOR CONTEXT|\[IMPORTANT: Background|\[Your active task list|"
    r"\[Planning state preserved|\[ASYNC |\[OUT-OF-BAND|Cronjob Response:|"
    r"A background (?:fan-out|subagent)|<session_summary>|<context_summary>|"
    r"\[SKILL|<skill>|<system_reminder>)", re.I)
_HUMAN_SOURCES = frozenset(('cli', 'desktop', 'web', 'webapp', 'tui', 'telegram', 'discord', 'slack',
    'whatsapp', 'signal', 'matrix', 'mattermost', 'email', 'sms', 'api', 'api_server',
    'feishu', 'dingtalk', 'wecom', 'bluebubbles', 'weixin'))

# Read-only wire adapter for native split_user_originated_turn / steer_user_row.
# These core modules are not public PLUGIN imports. Keep the narrow supported
# carrier grammar here, verified against actual SessionDB fixtures, not a loader
# escape hatch. Unknown/malformed carriers fail closed instead of choosing an
# older request. Nothing from a summary body is sent to the inference provider.
_STEER_OPEN = ('[OUT-OF-BAND USER MESSAGE — a direct message from the user, delivered '
    'once at this position; not tool output and not a new delivery when replayed from conversation history]')
_STEER_CLOSE = '[/OUT-OF-BAND USER MESSAGE]'
_SUMMARY_END = '--- END OF CONTEXT SUMMARY — respond to the message below, not the summary above ---'
_PRIOR_HEADER = '[PRIOR CONTEXT — for reference only; not a new message]'
_SUMMARY_DELIMITER = '[END OF PRIOR CONTEXT — COMPACTION SUMMARY BELOW]'
_SUMMARY_HEADERS = ('[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted into the summary below.',
                    '[CONTEXT SUMMARY]:')


# Native turn_context appends a *whole text part*: memory fence, then arbitrary
# pre_llm_call plugin text outside that fence. Keep boundaries until this part is
# removed; deleting just the XML span would disclose the unwrapped plugin tail.
# Match control frames at line boundaries, not ordinary prose mentioning them.
_MEMORY_PART = re.compile(
    r'(?m)^[ \t]*(?:<\s*(?P<close>/?)\s*memory-context(?=[\s/>]|$)|'
    r'\[System note:\s*The following is recalled memory context,\s*NOT new user input\.)', re.I)


# Enumerated producers reached by turn_context._merge_gateway_notes. Do not
# generalize to arbitrary '[Note:' / '[System note:' prose. See native fixtures:
# turn_stop_gates, plugins_activation_live, surface_switch, skills_index_delta,
# onboarding(_text), prompt_builder (HUD/Bot Screen), voice_live/tts_streaming,
# gateway reset/channel/voice sidecars, hook_output_spill, and deferred LSP's
# file_operations_lint formatter. Arbitrary unframed plugin text is not a marker.
_NATIVE_NOTE_PART = re.compile(
    r'(?m)^[ \t]*(?:'
    r'\[System note: (?:the language server reported problems in files you edited this turn, after '
    r'those tool results had returned\.|plugin [^\r\n]+ was installed and is live in this chat now '
    r'\(a Hermes note, not tool output\)\.|Onboarding continues; the [^\r\n]+ card is closed\.|'
    r"The user's previous session was stopped and suspended\. This is a fresh conversation with no prior context\.|"
    r'This (?:channel|thread) had an earlier Hermes session \(session_id: [^\r\n]+\) that was auto-reset\.|'
    r"This is the user's (?:very first message ever\.|first time opening the Hermes desktop app\.))|"
    r'\[System: (?:This conversation is now being answered on a different interface: |'
    r'These tools stay listed for this conversation \(dropping them would discard |'
    r'The skills available in this conversation changed after its system prompt was built\.)|'
    r'\[Note: (?:this message came from HUD mode — a small floating Hermes window |'
    r'this message is a delegation from a live spoken conversation\.|'
    r'the user interrupted your previous spoken reply before it finished\.\])|'
    r"Bot Screen: this profile's own headless desktop is (?:RUNNING on display |no longer running\.)|"
    r'\[Voice channel now: |\[plugin hook output truncated — [0-9,]+ chars; full content '
    r'(?:saved to |unavailable — spill write failed\])|'
    r'LSP diagnostics introduced by your earlier edit of [^\r\n]+ '
    r'\(the language server answered after that tool result returned\):)', re.I)


_MEMORY_TAG = re.compile(
    r'<\s*(?P<close>/?)\s*memory-context(?=[\s/>]|$)(?P<attrs>[^<>]*)(?P<end>>|(?=<)|$)', re.I)


def generation_context_part(text):
    match = _MEMORY_PART.search(text)
    if match:
        # Validate every fence in this part, including nested/orphan/truncated
        # fences. Otherwise a later rich part could be a private continuation.
        depth = 0
        for tag in _MEMORY_TAG.finditer(text[match.start():]):
            if tag.group('end') != '>' or tag.group('attrs').strip():
                raise ValueError('Malformed memory carrier')
            depth += -1 if tag.group('close') else 1
            if depth < 0:
                raise ValueError('Unseparable memory carrier')
        if depth:
            raise ValueError('Unfinished memory carrier')
        return text[:match.start()]
    return text


def generation_user_text(content, kind, summary):
    blocks = []
    def capture(part):
        blocks.append(part)
        return part
    raw = source_preview(content, role='user', limit=None, project_only=True, text_filter=capture)
    raw_start = 0
    def select(start=0, end=None):
        # Keep the exact interval in the joined parts, not a substring search:
        # the same words may occur in both a private summary and the live ask.
        nonlocal raw, raw_start
        raw_start += start
        raw = raw[start:end]
        raw_start += len(raw) - len(raw.lstrip())
        raw = raw.strip()
    select()
    if kind == 'steer':
        if not raw.startswith(_STEER_OPEN) or not raw.endswith(_STEER_CLOSE):
            return None
        select(len(_STEER_OPEN), -len(_STEER_CLOSE))
    elif summary or raw.startswith(_SUMMARY_HEADERS) or _SUMMARY_DELIMITER in raw:
        if kind not in (None, '', 'hidden'):
            return ''
        if _SUMMARY_DELIMITER in raw:
            prior, handoff = raw.split(_SUMMARY_DELIMITER, 1)
            if not handoff.lstrip().startswith(_SUMMARY_HEADERS):
                return None
            select(0, len(prior))
            if raw.startswith(_PRIOR_HEADER):
                select(len(_PRIOR_HEADER))
            if not raw:
                return None
        elif _SUMMARY_END in raw:
            handoff, _ = raw.split(_SUMMARY_END, 1)
            if not handoff.lstrip().startswith(_SUMMARY_HEADERS):
                return None
            select(len(handoff) + len(_SUMMARY_END))
            if not raw:
                # Rich carriers can have a non-text live block after the marker.
                # Without a readable projection, never replace it with an old ask.
                return None if content.startswith('\x00json:') else ''
        elif summary and raw.startswith(_SUMMARY_HEADERS):
            return ''
        else:
            return None
    elif kind == 'hidden':
        return ''
    elif raw.startswith(('[CONTEXT', '[PRIOR CONTEXT', '[OUT-OF-BAND')):
        return None
    elif _SYNTHETIC.match(raw) and not _NATIVE_NOTE_PART.match(raw):
        return ''

    # Unwrap summary/steer FIRST: notes inside a summary must not swallow its
    # end marker and turn a composite human row into a synthetic-only row.
    # Then sanitize the human interval part-by-part, before flattening. A
    # native injection's unframed plugin/diagnostic tail belongs to that part;
    # a separate subsequent human text part does not.
    projected, position, removed_note = [], 0, False
    raw_end = raw_start + len(raw)
    try:
        for block in blocks:
            left, right = max(0, raw_start-position), min(len(block), raw_end-position)
            if left < right:
                part = generation_context_part(block[left:right])
                note = _NATIVE_NOTE_PART.search(part)
                if note:
                    removed_note = True
                    part = part[:note.start()]
                projected.append(part)
            position += len(block) + 1  # project_only uses a newline between parts
    except ValueError:
        return None
    visible = source_preview('\n'.join(projected), role='user', limit=None)
    if (not visible and removed_note and kind in (None, '') and not summary
            and _NATIVE_NOTE_PART.match(content.lstrip())):
        # Only a standalone native text note is a proven synthetic row. An
        # image-only human turn with appended notes has no readable human ask;
        # fail closed instead of substituting an older request.
        return ''
    # A surviving control frame means an unsupported nested/malformed carrier.
    if _SYNTHETIC.match(visible):
        return None
    return visible or None


def generation_legacy_indices(conn, rows, anchor_id):
    """Read-only subset of native legacy display order: first physical identity.

    NULL is a lazy index, not corruption. Recover ordinary human rows using the
    exact native content/timestamp key; keep indexed logical slots authoritative.
    Unsupported legacy carriers are context barriers, never guessed identities.
    Future unindexed bodies are not read, even to hash/dedupe them.
    """
    anchor = next(row for row in rows if row['id'] == anchor_id)
    budget = 4 * 1024 * 1024

    def recover(row):
        nonlocal budget
        if row['role'] not in ('user', 'assistant') or row['_compressed_summary'] or row['display_kind']:
            return None
        # Only legacy ordinary rows have this exact native dedupe key. Summary
        # normalization and stable tool-call identities need their native index.
        record = conn.execute('''SELECT timestamp,tool_call_id,tool_calls,tool_name,
            CASE WHEN typeof(content)='text' AND length(CAST(content AS BLOB))<=?
                 THEN content END AS content FROM messages WHERE session_id=? AND id=?''',
            (min(GENERATION_MESSAGE_BYTES, budget), row['session_id'], row['id'])).fetchone()
        content = record['content']
        if content is None:
            return None
        budget -= len(content.encode('utf-8'))
        if (record['tool_calls']
                or (row['role'] == 'user' and (content.startswith('\x00json:')
                    or content.lstrip().startswith(('[CONTEXT', '[PRIOR CONTEXT', '[OUT-OF-BAND'))))):
            return None
        key = (row['role'], content, record['timestamp'], record['tool_call_id'],
               record['tool_calls'], record['tool_name'])
        return hashlib.sha256(repr(key).encode('utf-8', 'surrogatepass')).digest()

    def slot(row):
        return row['segment'], row['id'] if row['display_order'] is None else row['display_order']

    for row in rows:
        if row['display_order'] is not None and type(row['display_order']) is not int:
            raise HTTPException(422, 'Conversation timeline is unsupported')
        identity = row['display_identity']
        if identity is not None and (not isinstance(identity, bytes) or len(identity) != 32):
            raise HTTPException(422, 'Conversation timeline is unsupported')
    if anchor['display_identity'] is None:
        anchor['display_identity'] = recover(anchor)
        if anchor['display_identity'] is None:
            raise HTTPException(422, 'Selected legacy response needs a supported native timeline')
    cutoff = min(slot(row) for row in rows if row['display_identity'] == anchor['display_identity'])
    for row in sorted(rows, key=slot):
        if row['display_identity'] is None:
            identity = recover(row) if slot(row) <= cutoff else None
            if identity is None and row['role'] in ('user', 'assistant') and (
                    (not row['active'] and not row['compacted'])
                    or (row['role'] == 'assistant' and slot(row) <= cutoff)):
                # An unidentified tombstone might remove the selected message;
                # an earlier unidentified assistant might be its original copy.
                # Neither can authorize a later cutoff or resurrection. Do not
                # read a future tombstone body to resolve this uncertainty.
                raise HTTPException(422, 'Conversation legacy identity is ambiguous; nothing was sent')
            row['_legacy_unreadable'] = identity is None
            # A namespaced key cannot collide with native digest identities.
            row['display_identity'] = identity or ('legacy-unreadable', row['id'])
            if identity == anchor['display_identity']:
                cutoff = min(cutoff, slot(row))
    # Missing slots use the first physical occurrence, as native legacy display
    # does. Recovered copies inherit any earlier indexed slot in this segment.
    first = {}
    for row in rows:
        key = row['segment'], row['display_identity']
        first[key] = min(first.get(key, slot(row)[1]), slot(row)[1])
    for row in rows:
        if row['display_order'] is None:
            row['display_order'] = first[row['segment'], row['display_identity']]
    return 4 * 1024 * 1024 - budget


def strict_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate metadata key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-JSON constant')
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError('Expected metadata object')
    return value


def history_row_eligibility(role, active, compacted, kind, observed, summary, metadata, tool_calls=None):
    """Shared fail-closed projection: True visible, False private, None invalid.

    User carrier projection remains a later step; hidden summary/steer rows can
    carry a human ask. Assistant delivery discovery uses this exact same gate.
    """
    if role not in ('user', 'assistant') or not (active == 1 or compacted == 1) or observed:
        return False
    if role == 'assistant' and (kind or summary or tool_calls not in (None, '', '[]', 'null')):
        return False
    if role == 'user' and kind not in (None, '', 'steer', 'hidden'):
        return False
    try:
        if metadata is not None and (not isinstance(metadata, str) or len(metadata.encode()) > 4096):
            return None
        parsed = strict_object('{}' if metadata is None else metadata)
    except (ValueError, TypeError, RecursionError):
        return None
    if (any(parsed.get(k) for k in ('model_only', 'hidden', 'synthetic', 'thought', 'reasoning'))
            or parsed.get('channel') in ('analysis', 'reasoning', 'thought')):
        return False
    return True if parsed.get('channel') in (None, 'final', 'commentary') else None


def conversation_lineage(conn, home, session_id):
    """One bounded human/provenance policy for chooser, files, saves and inference."""
    # Native resume follows compression edges, not the entire historical
    # parent chain across resets/forks. Validate every consulted row without
    # bodies, including provenance on compression continuations.
    sid, seen, ancestry = session_id, set(), {}
    history_incomplete = False
    boundary_parent = False
    while sid:
        if not isinstance(sid, str) or not re.fullmatch(SESSION_ID_PATTERN, sid) or len(sid) > 160:
            raise HTTPException(422, 'Conversation ancestry is unsupported')
        if sid in seen:
            raise HTTPException(422, 'Conversation ancestry is unsupported')
        if len(seen) >= 100:  # native _resume_lineage_ids bound
            raise HTTPException(422, 'Conversation ancestry exceeds the bounded provenance check')
        seen.add(sid)
        session = conn.execute('''SELECT id,profile_name,hidden,source,parent_session_id,end_reason,
            CASE WHEN model_config IS NULL THEN '{}' WHEN typeof(model_config)='text'
                AND length(CAST(model_config AS BLOB))<=65536 THEN model_config ELSE 'INVALID' END AS model_config
            FROM sessions WHERE id=?''', (sid,)).fetchone()
        if session is None and ancestry:
            # Pruning does not guarantee retained parents. The verified
            # local segment remains usable; never guess missing history.
            history_incomplete = not boundary_parent
            break
        if (session is None or session['profile_name'] not in (None, '', profile_name(home))
                or session['hidden'] not in (None, 0) or session['source'] not in _HUMAN_SOURCES):
            raise HTTPException(404, 'Conversation is not available for generation in this profile')
        try:
            config = strict_object(session['model_config'])
            if not isinstance(config, dict) or '_delegate_from' in config:
                raise ValueError('Not proven human')
            for key in ('_branched_from', '_reset_from'):
                if key in config and (not isinstance(config[key], str) or not 1 <= len(config[key]) <= 160
                                      or not re.fullmatch(SESSION_ID_PATTERN, config[key])):
                    raise ValueError('Malformed lineage marker')
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(422, 'Conversation provenance is unsupported; nothing was sent') from None
        ancestry[sid] = (session, config)
        if session['parent_session_id'] in seen:
            raise HTTPException(422, 'Conversation ancestry is unsupported')
        if boundary_parent or (sid != session_id and session['end_reason'] != 'compression'):
            break
        # A fork may contain copied rows: check its immediate parent's known
        # provenance, but not the unrelated history beyond that boundary.
        boundary_parent = any(config.get(key) == session['parent_session_id']
                              for key in ('_branched_from', '_reset_from') if key in config)
        sid = session['parent_session_id']
    # Resume expands only verified compression edges, not arbitrary parents.
    # Inherited branch/reset markers bind to their original parent, not each
    # subsequent compression hop (native _resume_lineage_ids semantics).
    lineage = [session_id]
    while True:
        child, config = ancestry[lineage[-1]]
        parent = child['parent_session_id']
        if (parent not in ancestry or ancestry[parent][0]['end_reason'] != 'compression'
                or any(config.get(key) == parent for key in ('_branched_from', '_reset_from'))):
            break
        lineage.append(parent)
    lineage.reverse()
    return lineage, history_incomplete


def collect_generation(source, request, previous, *, expected_origin_digest=None):
    """Native timeline snapshot. Never hydrate a future body or write state.

    An exchange is one real user request and all its following visible assistant
    messages before the next real user request. The focal exchange contains ONLY
    its user request and the selected response. Unprovable legacy rows fence context.
    """
    with source.chooser_connection() as conn:
        source.chooser_schema(conn, {
            'sessions': ('id', 'profile_name', 'hidden', 'source', 'parent_session_id', 'model_config', 'end_reason'),
            'messages': ('id', 'session_id', 'role', 'content', 'active', 'compacted', 'display_order',
                         'display_identity', 'display_metadata', 'display_kind', 'observed', '_compressed_summary',
                         'message_uid', 'absorbed_message_uids', 'tool_calls'),
        })
        # Validate the exact delivery in THIS snapshot, before hydrating history.
        # A resolution in a prior transaction cannot authorize replacement text.
        if expected_origin_digest is not None:
            origin = conn.execute('''SELECT CASE WHEN typeof(content)='text'
                AND length(CAST(content AS BLOB))<=? THEN content END
                FROM messages WHERE session_id=? AND id=?''',
                (GENERATION_MESSAGE_BYTES, request.session_id, request.message_id)).fetchone()
            if (origin is None or origin[0] is None
                    or hashlib.sha256(origin[0].encode()).hexdigest() != expected_origin_digest):
                raise HTTPException(409, 'Delivery source changed or was removed. Choose the file again.')
        lineage, history_incomplete = conversation_lineage(conn, source.home, request.session_id)
        anchor = conn.execute('SELECT display_order,substr(display_identity,1,33) AS display_identity,role,active,compacted FROM messages WHERE session_id=? AND id=?',
                              (request.session_id, request.message_id)).fetchone()
        if anchor is None or anchor['role'] != 'assistant' or not (anchor['active'] == 1 or anchor['compacted'] == 1):
            raise HTTPException(422, 'Select an available assistant response')
        rows = []
        for segment, sid in enumerate(lineage):
            # Metadata only; NEVER read future bodies. Later physical rows can
            # be carried copies of earlier turns, so physical id is NOT a cutoff.
            # Segment-local slots and identities bound the logical selection.
            batch = conn.execute('''SELECT id,session_id,substr(role,1,32) AS role,active,compacted,
                    display_order,substr(display_identity,1,33) AS display_identity,
                    substr(display_metadata,1,4097) AS display_metadata,substr(display_kind,1,64) AS display_kind,
                    observed,_compressed_summary,substr(tool_calls,1,64) AS tool_calls,substr(message_uid,1,257) AS message_uid,
                    substr(absorbed_message_uids,1,65537) AS absorbed_message_uids
                FROM messages WHERE session_id=? ORDER BY id LIMIT ?''',
                (sid, GENERATION_ROW_LIMIT + 1 - len(rows))).fetchall()
            rows.extend(dict(row, segment=segment) for row in batch)
            if len(rows) > GENERATION_ROW_LIMIT:
                raise HTTPException(422, 'Conversation exceeds the bounded timeline scan; choose a shorter conversation')
        legacy_hydrated = generation_legacy_indices(conn, rows, request.message_id)
        representatives, positions, slots, identities, first_uid, removed = {}, {}, {}, {}, {}, {}
        row_keys, originals = {}, {}
        for row in sorted(rows, key=lambda row: row['id']):
            order, identity, uid = row['display_order'], row['display_identity'], row['message_uid']
            if uid is not None and (not isinstance(uid, str) or not uid or len(uid) > 256):
                raise HTTPException(422, 'Conversation message identity is unsupported')
            try:
                absorbed = json.loads(row['absorbed_message_uids'] or '[]')
                if not isinstance(absorbed, list) or any(not isinstance(v, str) or not v or len(v)>256 for v in absorbed):
                    raise ValueError('Invalid absorbed identities')
            except (ValueError, TypeError, RecursionError):
                raise HTTPException(422, 'Conversation message identity is unsupported') from None
            gone = not row['active'] and not row['compacted']
            copies = [identity, *(('uid', v) for v in ([uid] if uid else []) + absorbed)]
            removed.update(dict.fromkeys(copies, gone))
            # Superseded originals carry rewind flags too. They never supply
            # bodies, but keep the first logical position if a live copy exists.
            # Otherwise a carried protected head could move after its old answer.
            key = first_uid.get(uid, identity) if row['_compressed_summary'] else identity
            if uid and not row['_compressed_summary']:
                first_uid.setdefault(uid, identity)
            if type(order) is int:
                slot = (row['segment'], order)
                positions[key] = min(positions.get(key, slot), slot)
            if gone:
                continue
            if type(order) is not int:
                raise HTTPException(422, 'Conversation timeline index is unavailable; open it in Hermes first')
            slot = (row['segment'], order)
            scoped_identity = (row['segment'], identity)
            if identities.setdefault(scoped_identity, slot) != slot or slots.setdefault(slot, (identity, row['role'])) != (identity, row['role']):
                raise HTTPException(422, 'Conversation timeline identity is ambiguous')
            row_keys[row['id']] = key
            if not row['_compressed_summary']:
                originals.setdefault(key, row)
            chosen = representatives.get(key)
            if chosen is not None and chosen['role'] != row['role']:
                raise HTTPException(422, 'Conversation timeline identity is ambiguous')
            if chosen is None or (row['active'], row['id']) > (chosen['active'], chosen['id']):
                representatives[key] = row
            row['copies'] = copies
        anchor_key = row_keys.get(request.message_id)
        if anchor_key is None:
            raise HTTPException(422, 'Selected response is not available')
        # Exact selected physical response wins, never a later compaction copy.
        representatives[anchor_key] = next(row for row in rows if row['id'] == request.message_id)
        cutoff = positions[anchor_key]
        ordered = [row for key, row in sorted(representatives.items(), key=lambda item: positions[item[0]], reverse=True)
                   if positions[key] <= cutoff and not any(removed[copy] for copy in row['copies'])]
        if not ordered or ordered[0]['id'] != request.message_id:
            raise HTTPException(422, 'Selected response has been removed')
        hydrated = legacy_hydrated
        def text(row):
            nonlocal hydrated
            eligible = history_row_eligibility(*(row[k] for k in
                ('role', 'active', 'compacted', 'display_kind', 'observed', '_compressed_summary', 'display_metadata', 'tool_calls')))
            if eligible is not True:
                return '' if eligible is False else None
            kind, summary = row['display_kind'], row['_compressed_summary']
            if row.get('_legacy_unreadable'):
                return None
            if hydrated >= 4 * 1024 * 1024:
                return None
            content = conn.execute('''SELECT CASE WHEN typeof(content)='text' AND length(CAST(content AS BLOB))<=?
                THEN content ELSE NULL END FROM messages WHERE id=? AND session_id=?''',
                (min(GENERATION_MESSAGE_BYTES, 4 * 1024 * 1024 - hydrated), row['id'], row['session_id'])).fetchone()[0]
            if content is None:
                return None  # oversized/invalid: do not silently drop a required row
            hydrated += len(content.encode('utf-8'))
            if row['role'] == 'user':
                value = generation_user_text(content, kind, summary)
                if value == '' and summary and row['message_uid'] in first_uid:
                    # A known pure summary may stand for a human row with this
                    # exact durable UID. Recover that retained original, never
                    # substitute an unrelated earlier request. Removed originals
                    # and malformed carriers cannot authorize a fallback body.
                    original = originals.get(row_keys[row['id']])
                    return text(original) if original is not None and original['id'] < row['id'] else None
                return value
            visible = source_preview(content, role='assistant', limit=None)
            return '' if _SYNTHETIC.search(visible) else visible
        focal = text(ordered[0])
        if not focal:
            raise HTTPException(422, 'Selected response has no usable visible text or exceeds 64 KiB; nothing was sent')
        messages = [{'role': 'assistant', 'content': focal}]
        # Walk backwards only until the focal user and N complete earlier exchanges.
        truncated, count, found_user, pending = False, 0, False, []
        payload_size = len(focal.encode('utf-8'))
        for row in ordered[1:]:
            value = text(row)
            if value == '':
                continue
            if not found_user:
                if row['role'] != 'user':
                    continue
                if value is None:
                    raise HTTPException(422, 'Preceding user request is unreadable or exceeds 64 KiB; nothing was sent')
                messages.append({'role': 'user', 'content': value})
                payload_size += len(value.encode('utf-8'))
                found_user = True
                if previous == 0:
                    break
                continue
            if value is None:
                truncated = True
                break
            pending.append({'role': row['role'], 'content': value})
            payload_size += len(value.encode('utf-8'))
            if payload_size > GENERATION_PAYLOAD_BYTES - 16384:
                truncated = True
                break
            if row['role'] == 'user':
                if any(m['role'] == 'assistant' for m in pending):
                    messages.extend(pending)
                    count += 1
                pending = []
                if count == previous:
                    break
        if not found_user:
            raise HTTPException(422, 'No preceding real user request is available; nothing was sent')
        truncated = truncated or (history_incomplete and count < previous)
        messages.reverse()
        payload = json.dumps({'messages': messages}, ensure_ascii=False)
        if len(payload.encode('utf-8')) > GENERATION_PAYLOAD_BYTES:
            raise HTTPException(422, 'Escaped context exceeds the payload limit; nothing was sent')
        return payload, {'previous_exchanges': count, 'requested_exchanges': previous, 'truncated': truncated}

def bound_home():
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()).absolute()


def profile_name(home):
    return home.name if home.parent.name == "profiles" else "default"


class SourceAdapter:
    """On-demand source reads; no collection, native constructor, or migrations.

    Chooser previews are ephemeral, not bookmark metadata. Legacy availability
    checks remain identifier-only and accept existing non-assistant references.
    Reject linked stores; no SQLite immutable flag (live WAL must stay visible).
    A concurrent host prune can race a successful check; status is rechecked on
    every read. A bookmark is a reference, never a retention guarantee.
    """
    def __init__(self, home):
        self.home = home

    def availability(self, session_id, message_id=None):
        path = self.home / "state.db"
        try:
            if path.is_symlink() or any(p.is_symlink() for p in self.home.parents) or self.home.is_symlink():
                return "unavailable"
            if not path.exists():
                return "store_missing"
            if not path.is_file() or path.stat().st_nlink != 1:
                return "unavailable"
            conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
            try:
                conn.execute("PRAGMA query_only=ON")
                # Current native schema has profile_name. Older schemas without
                # it fail closed rather than treating a foreign row as local.
                row = conn.execute("SELECT profile_name FROM sessions WHERE id=?", (session_id,)).fetchone()
                if row is None or row[0] not in (None, "", profile_name(self.home)):
                    return "session_missing"
                if message_id is not None and conn.execute("SELECT 1 FROM messages WHERE id=? AND session_id=?", (message_id, session_id)).fetchone() is None:
                    return "message_missing"
                return "available"
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            return "unavailable"

    @contextmanager
    def chooser_connection(self):
        """Short-lived, bounded read transaction; never initialize/migrate native state."""
        conn = None
        try:
            path = self.home / "state.db"
            if any(p.is_symlink() for p in (self.home, *self.home.parents)):
                raise OSError("Linked home")
            # Also fence SQLite's sidecars: a safe main file is not sufficient.
            for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"), Path(str(path) + "-journal")):
                try:
                    info = candidate.lstat()
                except FileNotFoundError:
                    if candidate == path:
                        raise
                    continue
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise OSError("Unsafe native store")
            conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            deadline, ticks = time.monotonic() + 1, 0
            def budget():
                nonlocal ticks
                ticks += 1
                return ticks > 2000 or time.monotonic() > deadline
            conn.set_progress_handler(budget, 1000)
            conn.create_function("source_epoch", 1, source_timestamp, deterministic=True)
            conn.create_function('history_row_eligible', 8, history_row_eligibility, deterministic=True)
            conn.execute("BEGIN")
            yield conn
        except (OSError, sqlite3.Error, ValueError):
            raise HTTPException(503, "Conversation source is unavailable in this profile") from None
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def chooser_schema(conn, required):
        for table, columns in required.items():
            row = conn.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
            if row is None or row[0] != "table":
                raise sqlite3.DatabaseError("Unsupported native schema")
            # Names are adapter-owned constants, never request data.
            actual = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            if not set(columns) <= actual:
                raise sqlite3.DatabaseError("Unsupported native schema")

    def sessions(self, q="", limit=30, offset=0):
        with self.chooser_connection() as conn:
            self.chooser_schema(conn, {
                "sessions": ("id", "profile_name", "title", "source", "started_at", "ended_at", "last_activity_at", "hidden", "model_config", "parent_session_id", "end_reason"),
                "messages": ("session_id", "timestamp"),
            })
            # Apply the SAME provenance gate before timestamp ordering/windowing.
            # Only indexed per-session timestamps, never all message bodies.
            # Bound callback work too: short nested queries may not trigger the
            # connection VM progress handler. Exhaustion is an error, not an
            # apparently complete (but silently truncated) chooser.
            checks, deadline = 0, time.monotonic() + 1
            def eligible(sid):
                nonlocal checks
                checks += 1
                if checks > 10000 or time.monotonic() > deadline:
                    raise sqlite3.OperationalError('Conversation eligibility budget exceeded')
                try:
                    conversation_lineage(conn, self.home, sid)
                    return 1
                except HTTPException as exc:
                    if exc.status_code in (404, 422):
                        return 0
                    raise
            conn.create_function('eligible_conversation', 1, eligible)
            conn.create_function('human_source', 1, lambda value: value in _HUMAN_SOURCES, deterministic=True)
            rows = conn.execute("""
                SELECT id, substr(title,1,160) AS title, substr(source,1,64) AS source,
                    (SELECT MAX(value) FROM (
                        SELECT source_epoch(s.started_at) AS value UNION ALL
                        SELECT source_epoch(s.ended_at) UNION ALL
                        SELECT source_epoch(s.last_activity_at) UNION ALL
                        SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id=s.id
                            AND typeof(m.timestamp) IN ('integer','real')
                            AND m.timestamp BETWEEN 0 AND 253402300799
                    )) AS updated_at
                FROM sessions s WHERE (profile_name IS NULL OR profile_name='' OR profile_name=?)
                    AND COALESCE(hidden,0)=0 AND human_source(source)=1 AND eligible_conversation(id)=1
                ORDER BY updated_at DESC, id DESC LIMIT ?
            """, (profile_name(self.home), SOURCE_SESSION_WINDOW + 1)).fetchall()
        items = []
        for row in rows[:SOURCE_SESSION_WINDOW]:
            sid = row["id"]
            if not isinstance(sid, str) or not 1 <= len(sid) <= 160 or not re.fullmatch(SESSION_ID_PATTERN, sid):
                continue
            source = source_label(row["source"], 64)
            items.append({"id": sid, "title": source_label(row["title"], 160) or f"{source or 'Conversation'} · {sid}",
                          "updated_at": row["updated_at"], "source": source})
        return source_page(items, q, limit, offset, SOURCE_SESSION_WINDOW,
                           len(rows) > SOURCE_SESSION_WINDOW, ("id", "title", "source"))
