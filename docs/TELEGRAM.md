# Telegram Shelf panels and derivative offers

**Unreleased backend feature. Verified offline against official Hermes v0.22.5
(`bf0203a794a07aac3ff764972ab9087baa4e4f4e`) with real PTB objects and a capture
transport—not live Telegram delivery.** No production installation or restart was
performed for this verification.

## What the user sees

On an authorized Telegram connection, `/shelf` sends a short **Shelf · N saved**
message with attached buttons: **Add**, up to five recent entries, and **Browse more**.
The same controls work in private chats and groups/topics. Browse edits that message;
it does not replace your typing keyboard. Select an entry and choose **Send file**
to receive its attachment. Metadata-only entries say **No file attached**; missing
or unsafe files say **File unavailable**.

**Add** and `/shelf add` save a recent file from this conversation without a model
call or agent handoff. One eligible file saves immediately and is read back before
confirmation. Several files in the newest delivery open a chooser with **Cancel**;
nothing is saved until you choose. **View saved file** opens the saved entry and its
Send file button. An already-registered root/path returns **Already saved** without
changing the existing card or revision.

Optional `/shelf add My title #Tag-one, Tag-two --description "My description"`
preserves those fields. Defaults are the filename as title, an image/document kind,
and empty tags/description. No recent file found? Ask Hermes to save it in normal chat.

Add recognizes explicit standalone `MEDIA:` local-file references in eligible
assistant responses from the **active segment of this conversation**. It does not
scan folders, infer files from links/prose, inspect another conversation, or follow
compressed summaries/ancestor history. Older or compressed-away deliveries can need
the normal-chat fallback. A source reference is not proof that Telegram previously
received the file. See [exact source and safety limits](DETERMINISTIC_ADD.md).

The advanced override `/shelf add [title] [#tags] --file root:relative-path
[--description "text"]` remains separate. Complete metadata saves directly;
omitted metadata is filled by the existing agent under explicit injection consent.
Each such handoff gets a fresh token bound to its file, supplied fields, owner,
profile and exact session. Only this **advanced missing-metadata handoff** is refused
in groups/topics on v0.22.5; use a private chat or supply all metadata. Ordinary Add
does not use injection and is not subject to that restriction.

## Operator setup (not applied automatically)

1. Use the intended profile and its normal authorized Telegram gateway. The plugin
   consumes the host-supplied PTB `Application` through
   `ctx.register_platform_handler`; it never opens a second bot or reads a token.
2. Native panels require **in-process** plugin execution. If the operator chooses
   `plugins.isolation: host`, the plugin retains a simple text list/search fallback.
   Do not weaken isolation to obtain inline panels.
3. Create the operator-owned file
   `<profile-home>/plugin-data/delivery-shelf/telegram-owners.json` containing a JSON
   array of the human owners' numeric Telegram IDs **as strings**, for example:
   ```json
   ["123456789"]
   ```
   This ID is fictional. Substitute the intended human owner; never a username,
   display name, bot ID, chat ID, or wildcard. Missing, malformed, symlinked,
   oversized, or non-regular policy files deny native access. Maximum 50 IDs,
   4 KiB policy. Keep the policy private and writable only by the operator.
4. Ordinary Add and file retrieval need **no injection permission**. Only if you
   want advanced `--file` commands to generate missing metadata, explicitly enable
   `plugins.entries.delivery-shelf.allow_gateway_injection: true` in that profile.
   This is separate from owner policy; queuing is not proof of saving.
5. Retain narrow `allowed-roots.json` policy. No button/tool expands roots.
6. Start a fresh session to activate the registered tool and frozen prompt guidance.
   After updating native handler code, restart the owning gateway when authorized:
   existing PTB handlers may remain wired after hot reload. An unloaded controller
   refuses old buttons; it does not take over another controller's panels.

The owner file is re-read before every panel send, callback, and guarded Add save.
Removing an ID revokes existing buttons too. This policy is **additional** to normal
Hermes command admission, not a mirror of gateway pairing/allowlists: when revoking
a person, remove them from this owner policy as well. Native callbacks have no
public generic gateway authorization API. A group panel's visible text is visible
to that group even though only the issuing owner can operate it; use a private chat
for private catalog metadata.

## Native handler reload caveat

An offline reproduction against installed host commit
`7b46bc10064d71951ef49734d762123bc0ac896b` proves that initial/late loading works,
but force rediscovery on the same Telegram Application can detach Shelf's command
from its native panel. `BasePlatformAdapter._wire_plugin_handlers` caches
`(plugin_name, factory.__qualname__)`. Rediscovery unloads the first controller and
registers a new controller with the same factory name; the adapter skips that new
factory, leaving its `application` unset. A successful reload receipt or command
registration does not establish working native callbacks. The core `/model`
picker still works because it sends through the adapter's existing bot, not through
the replaced plugin controller.

`tests/native_telegram_lifecycle.py` reproduces this with the actual PluginManager,
TelegramAdapter wiring, native dispatcher/task context, forum route, real PTB
Application/Update, and captured Bot API transport. It verifies native `/model`
markup during the failure and recovery after rebuilding the native Application,
including owner/topic callback denial. This is a **host limitation characterization
and recovery test**, not a claim that plugin hot reload was fixed.

For affected hosts, finish installing the reviewed plugin version, then use an
authorized **graceful restart of only its owning gateway** so native handlers bind
at startup. A second force reload alone repeats the problem. Preserve owner policy,
roots and isolation; do not borrow the adapter's private bot, rename factory keys
to bypass host deduplication, or patch handler tables. Test `/shelf` and a browse
button in the intended topic after restart before claiming live restoration.
Until upstream supports replacing/removing native factory registrations safely,
repeat that activation check after plugin rediscovery. File sending uses the same
native Application and therefore depends on this activation boundary too.

## Direct file retrieval (no model call)

- Open `/shelf`, tap an entry, then **Send file**. The file arrives as a native
  document attachment in the same chat/topic, not a server path.
- `/shelf dl 1` or `/shelf download 1` sends item 1 of **your last displayed list**.
  `/shelf search <query>` produces up to 20 numbered results; an inline page numbers
  its own five results. Numbers are not recalculated against changing recent order.
  Starting a new list disables the previous snapshot. Its replacement becomes
  selectable only after a matching native send/edit acknowledgement; snapshots
  expire after ten minutes. Concurrent list updates are refused rather than reordered.
  After an uncertain list delivery, numbers stay disabled for that result context;
  refresh to use unnumbered entry buttons → **Send file**, or use recent shortcuts.
  Text-only fallback lists never authorize numbers because the host return path
  has no send receipt.
- `/shelf r3` directly attempts the three most recently updated **attached entries**.
  Use `r1` through `r5`. Reference-only entries are excluded. A missing/unsafe file
  counts as unavailable; it is not replaced with an older entry. Fewer attached
  entries than requested are reported separately. No list selection is required.

All retrieval paths are deterministic: no agent, tool handoff, gateway injection,
transcript retrieval, or metadata writes. They work in authorized groups/topics
without enabling agent-injection permission. Only the saved file field is used;
description text is never interpreted as a path. Files remain live references.

Each request revalidates owner, profile, current session, lifecycle, entry revision,
root policy and file identity. File reads run off-loop through the approved descriptor
opener into a bounded byte snapshot, rejecting changes during reading and before send
authorization. No pathname is handed to PTB to reopen. Maximum 10 MiB per file,
five sequential files / 50 MiB per batch. ZIP is opaque: never extracted or previewed.
A change after the final authorization point cannot recall bytes already being sent.

An in-flight per-owner/chat/topic lock rejects overlapping sends. A Send file action
is single-use, including on ambiguous transport failure. Failed sends are never
retried automatically or rerouted to the root chat; a batch stops after an uncertain
POST and reports unattempted entries. Inspect the chat before explicitly requesting
again. This is not durable exactly-once delivery across process restarts.

Native-transport-unavailable or isolated hosts give a concise Desktop/Dashboard
fallback; they do not silently invoke a model. Snapshot state is owner/chat/topic/
profile/session scoped, bounded to 128 lists, and cleared on unload/reconnect/reset.
Uncertainty fences are non-evicting for the controller lifetime; reconnecting does
not silently restore an ambiguous mapping. Their bounded overflow disables numeric
publication, not explicit entry-based retrieval.
`tests/native_downloads.py` exercises the official loader, gateway dispatcher and
real PTB forum updates with captured multipart bytes and rejecting inference/injection
mocks. It does not send to live Telegram.

## Agent-driven derivative offers

`delivery_shelf_offer_update` takes exactly:

```json
{"id":"0123456789abcdef0123456789abcdef","file":{"root":"workspaces","path":"report-revised.pdf"}}
```

The ID is illustrative, not a real registration. Stable system-prompt guidance asks
the agent to call this tool after creating a concrete **new derivative** of a known
registered file. It validates that entry and the new safe file before sending:

- **Update registration**
- **Keep current**

An offer does not save. Approval changes **only the file reference on the same
entry ID**, using the offered revision as a compare-and-swap precondition. Title,
tags, description, project, kind, session reference and creation time are preserved;
revision and update time advance. The callback reads that exact ID back and compares
it before displaying **Updated**. A conflicting UI/tool edit prevents retargeting.
Neither source file is modified or deleted; this is not a version-history archive.

**Editing the same registered path is silent**, regardless of content, hash or
mtime. Approved aliases resolving lexically to the same absolute path are also
silent. No watcher, global scan, post-write guessing or comprehensive automatic
lineage detection is implemented. The model must know and declare the relationship.
One new file can be offered per call; the same entry/output/session is deduplicated
for ten minutes. A different output can receive its own offer.

On CLI, non-Telegram, missing context/owner permission, or unavailable native
transport, the tool returns **unsupported**, explicitly stating no offer was sent
and nothing changed. Ask for explicit user confirmation, then use the existing
`delivery_shelf_update` tool with the latest revision. Never claim a button was
shown on those surfaces.

## State and safety boundaries

- Opaque panel IDs and fresh per-render action generations contain no paths or executable instructions. Namespace:
  `shelf:`. Actual choices are looked up in plugin-owned state, not interpreted from
  text. The controller checks owner, chat, topic, message, Application, connection
  generation, owning profile, expiry and consumed/busy state. Claiming an action
  invalidates that keyboard; replacements are staged until matching acknowledgement.
  Failed/cancelled edits retire the panel before attempting an error confirmation.
  Send file retains its separate random, one-shot action ID format.
- Topics and the inbound reply anchor are carried to PTB explicitly when supplied.
  An unexpected returned chat/topic disables the panel. No root-chat retry occurs.
- Reset/delete hooks invalidate outstanding panels, deterministic Add choices and
  advanced handoff requests. The advanced handoff's backend request guard also compares the expected session ID and route with the current
  task-bound session context; stale/invented tokens, changed profiles or omitted
  tokens while a request is pending are denied. The legacy environment fallback is
  not used as native identity. Without the required host lifecycle/context surfaces,
  these guarantees are not supported.
- Native callback lifecycle checks are hook-driven. This is not an atomic transaction
  with Hermes's session store or a durable cross-process approval system. The tool
  guard prevents a delayed Add from saving into a reset session. The plugin does not
  claim that it can authenticate arbitrary model intent or prevent a user/agent with
  separately authorized normal CRUD access from making a different explicit save.
- PTB sends/edits/acknowledgments stay on their event loop. Policy reads, catalog
  construction, queries, writes, readback and controller-lock acquisition in async
  send/callback paths run in context-preserving workers. The controller lock protects
  only memory state; neither SQLite waits nor policy/host calls hold it.
  Writes obtain `BEGIN IMMEDIATE` before rechecking root/file policy and the atomic
  lifecycle/owner/expiry/one-shot authorization gate. Reset, unload, reconnect or
  revocation while waiting prevents authorization. Once the gate authorizes a commit,
  it may finish after a reset; cancellation cannot undo an already-authorized write.
  CAS still checks the offered revision in the transaction. A guarded registration's
  file claim is retained even after a commit/readback failure: inspect before retrying.
- State is memory-only: ten-minute TTL, at most 128 panels, 128 requests and 128
  dedupe keys per controller, at most eight choices per deterministic Add delivery
  or 32 files per advanced agent-handoff request. Expired/oldest entries
  are evicted on interaction. Unload/reconnect clears outstanding state; restart
  expires all buttons. No transcripts or approval files are persisted. A separate
  bounded set retains up to 128 retired session IDs for the controller lifetime, so
  a pinned old agent turn cannot offer/register after reset. Rather than evicting
  those safety markers, overflow (or a reset hook missing its old session ID) fences
  native panels/guarded saves until an operator-authorized gateway restart. Explicit
  text/fully specified command saves remain available. Connection replacement also
  fences sends that were already in flight.
- Root/file policy is checked again at approval. Existing file rules still apply:
  no symlinks/hard links, sensitive filenames, hidden paths, unsupported types or
  files over 10 MiB. These are filename/path checks, not content-based secret detection.
- Failed/ambiguous confirmation does not display success. A commit can succeed before
  a network/readback failure: inspect the entry before retrying. There is no distributed
  transaction between SQLite and Telegram.

## Verification and known compatibility issue

`tests/test_telegram.py` uses actual `Application`, `Update`, callback handlers and
`InlineKeyboardMarkup` with a `BaseRequest` capture transport. `tests/native_telegram.py`
loads through the official plugin manager, invokes the actual gateway dispatcher
(including sync-command→awaitable handling), captures native consent/injection,
registers/searches real SQLite records, applies an approved derivative, runs the native
reset hook, and tests the real isolated host's text fallback. All files/IDs are fictional.
`tests/test_telegram_review.py` adds completed-Add→explicit-file request, two-participant
shared-topic refusal, real SQLite contention/heartbeat, concurrent click, and waiting
worker reset/unload/reconnect/expiry/owner/root revocation regressions. The research
origin-authority probe exercises real public injection, TelegramAdapter and session
authority admission, with execution scheduling disabled and no connected adapter.

The v0.22.5 Doctor reports four tools and no findings. Its broader catalog scanner
emits one disclosed warning: it classifies imports from `gateway.session_context`
as private, although official plugin docs explicitly recommend `get_session_env`.
The implementation additionally uses public `bound_session_key()` to reject the
accessor's legacy ambient-environment fallback. No private adapter APIs are used.
The warning is not hidden; `native_contract.py` checks only that known warning and
fails on any other warning. This remains a compatibility/catalog-review caveat.

`tests/native_recent_add.py` separately exercises deterministic Add with injection
permission false and rejecting LLM/injection facades, including its failed-edit and
post-wait source guards. `tests/native_downloads.py` covers exact multipart bytes,
unacknowledged numbered-list refusal and foreign-profile query denial. Add → View
saved file uses the same guarded detail renderer as ordinary browsing.

These tests do **not** establish live Telegram delivery, real client layout, actual
forum/DM-topic acceptance by Telegram servers, model adherence to the new derivative
guidance, production routing, or full Electron-shell behavior. Those require separately
authorized acceptance testing. UI sources and built bundles are not changed by this feature.
