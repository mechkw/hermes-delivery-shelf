# Telegram Shelf panels and derivative offers

**Unreleased backend feature. Verified offline against official Hermes v0.22.5
(`bf0203a794a07aac3ff764972ab9087baa4e4f4e`) with real PTB objects and a capture
transport—not live Telegram delivery.** No production installation or restart was
performed for this verification.

## What the user sees

On an authorized Telegram connection, `/shelf` sends a short **Shelf · N saved**
message with genuine attached `InlineKeyboardMarkup`: **Add** first, up to five
recent entries (each opens details), and **Browse more** last. Browse edits that
same message; it does not replace the user's typing keyboard. There are no file
uploads or filesystem browsing controls.

**Add** queues a request for the most recent delivered artifact or related set
already identifiable in this conversation's context. It does not search folders,
choose by modification time, retrieve another conversation, or copy transcripts.
If the intended artifact is absent or ambiguous, the agent must ask a focused
question. The panel says **Requested**, explicitly **nothing saved yet**. The
agent calls `delivery_shelf_register` and then `delivery_shelf_search` for exact
readback before confirming saved details. This is model-guided selection, not a
deterministic artifact detector.

`/shelf add` requests the same current-context workflow. The explicit override
remains `/shelf add [title] [#tags] --file root:relative-path
[--description "text"]`. Complete metadata saves directly; omitted metadata is
filled by the existing agent. Ordinary query commands remain text searches.

Each native explicit-file metadata handoff gets a **fresh request token**, even
after a successful bare Add. That token binds the selected file, supplied metadata,
owner, profile and exact current session route/generation. The agent may fill only
missing metadata. Earlier requests remain guarded for their related artifact sets;
omitting a token is not a workaround, and a successful file claim cannot be replayed.

**Group-chat limitation on v0.22.5:** clicking Add, bare `/shelf add`, or an
explicit-file command missing metadata refuses **before queueing** in Telegram
groups/topics. The refusal explains that the host cannot safely bind the clicking
owner and suggests a private chat or supplying all metadata. Fully specified saves,
browsing and Update registration / Keep current panels still work in groups.
This conservative restriction also applies to groups configured for per-user sessions.
Keyed host injection restores the session's original participant. Public `origin=`
injection preserves identity on the classic path, but under the session authority it
can return accepted and subsequently reject a different participant against the last
committed source. There is no public prequeue acknowledgment pinning both owner and
current generation. The plugin does not weaken owner/session guards to hide this gap.

## Operator setup (not applied automatically)

1. Use the intended profile and its normal authorized Telegram gateway. The plugin
   consumes the host-supplied PTB `Application` through
   `ctx.register_platform_handler`; it never opens a second bot or reads a token.
2. Native panels require **in-process** plugin execution. If the operator chooses
   `plugins.isolation: host`, the plugin retains text commands and reports that
   inline panels are unavailable. Do not weaken isolation just to hide this limit.
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
4. For Add's agent handoff, explicitly enable
   `plugins.entries.delivery-shelf.allow_gateway_injection: true` in that profile.
   This is separate from the owner policy and from existing gateway permissions.
   The host rechecks injection consent; queuing is not proof of saving.
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

- Opaque random callback IDs contain no paths or executable instructions. Namespace:
  `shelf:`. Actual choices are looked up in plugin-owned state, not interpreted from
  text. The controller checks owner, chat, topic, message, Application, connection
  generation, owning profile, expiry and consumed/busy state.
- Topics and the inbound reply anchor are carried to PTB explicitly when supplied.
  An unexpected returned chat/topic disables the panel. No root-chat retry occurs.
- Reset/delete hooks invalidate outstanding panels and Add requests. Add's backend
  request guard also compares the expected session ID and route with the current
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
  dedupe keys per controller, at most 32 files per Add request. Expired/oldest entries
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

These tests do **not** establish live Telegram delivery, real client layout, actual
forum/DM-topic acceptance by Telegram servers, model adherence to the new derivative
guidance, production routing, or full Electron-shell behavior. Those require separately
authorized acceptance testing. UI sources and built bundles are not changed by this feature.
