"""Bounded read-only native source adapter; no transcript or delivery index is stored.

Like Bookmarks' source chooser, this reads the native profile store directly.
SessionDB's display/ancestor API can scan full legacy history and SELECT * hydrates
private/tool fields. This deliberately narrower adapter reads only eligible
assistant content in the invoking segment, never materializes display indices,
and supports retained NULL/BLOB display identities without using them as strings.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
import time

WINDOW = 40
CONTENT_BYTES = 65536
MAX_FILES = 8
MISSING = 'No recent file found. Ask me to save the file in normal chat.'


@dataclass(frozen=True)
class Delivery:
    row: int
    cutoff: int
    digest: str
    paths: tuple[str, ...]


@contextmanager
def connection(home):
    conn = None
    try:
        path = home / 'state.db'
        if any(p.is_symlink() for p in (home, *home.parents)):
            raise ValueError('Linked source home')
        for candidate in (path, Path(str(path)+'-wal'), Path(str(path)+'-shm'), Path(str(path)+'-journal')):
            try:
                meta = candidate.lstat()
            except FileNotFoundError:
                if candidate == path:
                    raise
                continue
            if not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1:
                raise ValueError('Unsafe source')
        conn = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=1)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        deadline, ticks = time.monotonic()+1, 0
        def budget():
            nonlocal ticks
            ticks += 1
            return ticks > 2000 or time.monotonic() > deadline
        conn.set_progress_handler(budget, 1000)
        conn.execute('BEGIN')
        for table, required in {
            'sessions': {'id', 'profile_name'},
            'messages': {'id', 'session_id', 'role', 'content', 'active', 'display_kind',
                         'observed', '_compressed_summary', 'tool_calls'},
        }.items():
            if conn.execute('SELECT type FROM sqlite_master WHERE name=?', (table,)).fetchone()[0] != 'table':
                raise ValueError('Unsupported source schema')
            if not required <= {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}:
                raise ValueError('Unsupported source schema')
        yield conn
    except (OSError, sqlite3.Error, TypeError, ValueError):
        raise ValueError('Recent files are unavailable in this conversation. Ask me to save the file in normal chat.') from None
    finally:
        if conn is not None:
            conn.close()


def explicit_paths(content):
    if not isinstance(content, str):
        return ()
    if content.startswith('\x00json:'):
        try:
            blocks = json.loads(content[6:])
        except ValueError:
            return ()
        if not isinstance(blocks, list):
            return ()
        content = '\n'.join(b['text'] for b in blocks if isinstance(b, dict)
                            and b.get('type') in ('text', 'output_text') and isinstance(b.get('text'), str))
    paths, fence = [], False
    for line in content.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fence = not fence
            continue
        if fence:
            continue
        # Only the transport's explicit local delivery marker, never prose paths,
        # markdown code, URLs, inferred filenames, or tool output.
        match = re.fullmatch(r'MEDIA:\s*(/[^\r\n]+)', line.strip())
        if match and match[1] not in paths:
            paths.append(match[1])
    if len(paths) > MAX_FILES:
        raise ValueError('Too many files in the recent delivery. Ask me to save the selected file in normal chat.')
    return tuple(paths)


def recent(home, profile, session_id, *, cutoff=None):
    if not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', session_id):
        raise ValueError('No current conversation. Ask me to save the file in normal chat.')
    with connection(home) as conn:
        owner = conn.execute('SELECT profile_name FROM sessions WHERE id=?', (session_id,)).fetchone()
        if owner is None or owner[0] not in (None, '', profile):
            raise ValueError('Conversation unavailable')
        if cutoff is None:
            cutoff = conn.execute('SELECT COALESCE(MAX(id),0) FROM messages WHERE session_id=?', (session_id,)).fetchone()[0]
        rows = conn.execute('''SELECT id,
            CASE WHEN typeof(content)='text' AND length(CAST(content AS BLOB))<=? THEN content END AS content
            FROM messages WHERE session_id=? AND id<=? AND active=1 AND role='assistant'
            AND COALESCE(display_kind,'')='' AND COALESCE(observed,0)=0
            AND COALESCE(_compressed_summary,0)=0 AND COALESCE(tool_calls,'') IN ('','[]','null')
            ORDER BY id DESC LIMIT ?''', (CONTENT_BYTES, session_id, cutoff, WINDOW))
        for row in rows:
            # Do not silently skip a newer oversized answer to save an older file.
            if row['content'] is None:
                raise ValueError('Recent delivery is too large to inspect. Ask me to save the file in normal chat.')
            paths = explicit_paths(row['content'])
            if paths:
                return Delivery(row['id'], cutoff, hashlib.sha256(row['content'].encode()).hexdigest(), paths)
    return None


def candidates(api, home, delivery):
    """Map literal absolute references to existing operator roots, never search."""
    roots = api.allowed_roots(home)
    result = []
    for raw in delivery.paths:
        path = Path(raw)
        # Path() normalizes dot components; reject before constructing a FileRef.
        if not path.is_absolute() or any(p in ('', '.', '..') for p in raw.split('/')[1:]):
            raise ValueError('Recent file is not available under the current file policy.')
        matches = sorted(((alias, root) for alias, root in roots.items() if path.is_relative_to(root)),
                         key=lambda pair: (-len(pair[1].parts), pair[0]))
        if not matches:
            raise ValueError('Recent file is outside the approved Shelf locations.')
        alias, root = matches[0]
        ref = api.FileRef(root=alias, path=path.relative_to(root).as_posix())
        with api.open_file(home, ref):
            pass
        if ref.model_dump() not in result:
            result.append(ref.model_dump())
    return result


def metadata(api, ref, session_id, supplied=None):
    name = Path(ref['path']).name
    image = Path(name).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    return api.EntryInput.model_validate(dict(title=name[:160], description='', tags=[], project='',
        kind='image' if image else 'document', file=ref, session_id=session_id) | (supplied or {}))


def supplied_metadata(raw):
    import shlex
    parts = re.split(r'\s+--description(?:\s+|$)|^--description(?:\s+|$)', raw, maxsplit=1)
    values = {}
    if len(parts) == 2:
        words = shlex.split(parts[1])
        if len(words) != 1:
            raise ValueError('Quote the description after --description.')
        values['description'] = words[0]
    head = parts[0].strip()
    if '--' in head:
        raise ValueError('Use a title, #tags, or --description with Add.')
    tags = re.split(r'(?:^|\s)#', head, maxsplit=1)
    if tags[0].strip():
        values['title'] = tags[0].strip()
    if len(tags) == 2:
        values['tags'] = [tag.strip() for tag in tags[1].split(',')]
    return values
