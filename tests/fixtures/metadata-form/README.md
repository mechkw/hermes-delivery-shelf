# Metadata form fixture (not host integration)

`ui/MetadataForm.jsx` is a reusable, unmounted React form. It imports the existing
`@saved/presentation` adapter and the parent-owned draft/error modules. Nothing in
Desktop, Dashboard, `ShelfEditor` or the backend routes to it yet.

## Local props and adapter

The component's JSDoc defines the local contract. `ownerKey` and `sourceKey` are
required nonempty UI identity fences, **not authorization**. Initial values and
`default`/`user` provenance seed a new identity; changes to initial props with the
same identity do not overwrite edits. `generationAllowed` must be explicitly true
to offer generation. The future authenticated adapter must additionally enforce
host eligibility, permits, validation and source/owner binding.

- `generate(request)` receives a unique request ID, identity, sorted
  `requested_fields` and exact `supplied_metadata`. It resolves with exactly the
  requested fields. Resolution promises terminal remote work; rejection is treated
  as uncertain, not proof of teardown. It never saves.
- `cancel(request)` / `status(request)` return `unknown`, or a status with
  `state: stopped | not_started | quarantined`, `safeToSave: true` and an explicit
  boolean `canGenerate`. Safe quarantine need not grant another generation permit.
  The adapter must certify the durable meaning; these booleans are not proof from
  this component. Stop fences immediately. Unknown work blocks both Save and new
  generation. An explicit status button makes one bounded check (two seconds),
  with no polling or regeneration. A late timed-out callback cannot unlock Save.
  After a same-draft safe reply with `canGenerate: false`, the same control remains
  “Check generation status”. It retains the exact stopped/quarantined request and
  its original adapter. Explicit clicks make bounded status reads, not Generate or
  Save requests. False/unknown/malformed/error/timeout retains this retry path and
  does not revoke previously certified nongenerating Save safety. Only a validated
  safe reply with `canGenerate: true` releases this local permit gate; a later,
  separate Generate click also requires current `generationAllowed` and eligible
  fields. Flipping that prop alone never establishes teardown or permit release.
  Owner/source reset, remount and superseding work fence late discovery replies;
  permits and discovery feedback cannot migrate into a different draft. This is
  a minimal local adapter contract, not an implemented native-host status API.
- `save({ownerKey, sourceKey, metadata, generation_policy: 'never'})` receives all
  three fields, including explicit empty description/tags. Save never generates.
  Rejections may expose `{code: 'metadata_invalid', message: 'Invalid metadata:
  FIELD/RULE'}` for the fixed-message mapper; arbitrary prose never renders.
  Structured errors associate with/focus the affected field after explicit Save.
  An indexed tag error targets its existing editable row, or pending entry when
  that is the last draft tag. Collection/unavailable-index errors safely target
  the pending entry. Edits/removal clear feedback; identity-scoped row refs and
  Save-response fencing prevent an old error from focusing a new owner's row.
  Title has no frontend policy gate: even an empty or otherwise invalid initial
  title is submitted exactly for authoritative rejection. The required-field
  semantic remains, with `noValidate` so native validation cannot replace the
  protocol. Operation/saving/malformed-result safety gates still block Save.

The adapter still owns authenticated validation (Unicode-14 included), admission,
publication/idempotency, cancellation teardown, permissions and permit accounting.
There is no model/provider/backend call in this fixture. UI cancellation alone
cannot establish backend safety. Unmount fences results and makes a best-effort
cancel; a future host adapter must retain operation ownership beyond UI teardown.

## Exact values

Tags use ordinary editable rows and a single-line-looking entry control. Enter or
Add tag appends one exact tag without submitting. Remove deletes only that row;
editing to an empty string preserves that row until explicitly removed. No comma,
newline, JSON or escape syntax is interpreted; nothing is trimmed, deduplicated,
case-folded or sorted. The textarea primitive preserves invalid embedded LF rather
than silently dropping it like a single-line input. Initial CR/CRLF and other
invalid strings stay exact in draft/Save even though textarea DOM rendering uses
browser-normalized line endings; only explicit edits replace a value.

Nonempty pending entry is already part of the draft: explicit Save includes it
once without requiring Enter, and Generate treats it as user-authored. Clearing
all rows and pending entry restores eligibility. Every tag action advances the
same all-field revision fence, including change-back and removal. Identity reset
clears pending text. Authoritative validation remains an adapter duty; the actual
fixed-message mapper supplies error feedback and invalid values remain intact
until corrected. No local Title validator duplicates server policy. Malformed
generation still applies nothing and blocks Save
until a manual edit or a subsequent valid Generate.

A valid but revision-stale Generate response fills nothing and emits exactly
“Your edits were kept.” as one polite nonerror status, without field association
or focus movement. Edits and explicit actions clear it. Malformed responses stay
errors, including when revisions changed; cancelled, old-owner/source or otherwise
fenced results do not announce in another draft. No idle instructions, successful
generation announcement or successful-Save announcement is added.

## Exercise

From the repository root:

```sh
METADATA_FORM_PROOF=../evidence/shelf-metadata-form-correctness-repair/browser-run node tests/metadata-form-browser.mjs
node --test tests/metadata-draft.test.mjs tests/metadata-errors.test.mjs
```

The runner uses dependencies already installed in `HERMES_UI_SOURCE` (default:
`~/.hermes/hermes-agent`); it does not install anything or change package files.
It compiles the actual ReactDOM form and both repository presentation adapters
with real installed UI controls/CSS. Only transport and theme-token configuration
are fictional. It starts an owned loopback server and an isolated headful Chromium
on the available X11 display, with an owned Xvfb fallback. Temporary bundles,
browser and server are removed in `finally`; inputs and cleanup are read back.
The runner's test-only mount transform exposes adapter/eligibility prop changes
and a React key for real unmount/remount lifecycle checks; it does not change the
fixture source or the component under test. `METADATA_FORM_CASE` selects one exact
scenario substring for focused diagnostics (two surfaces); such runs are labelled
filtered and never count as a complete suite. Browser CDP identity plus live `/proc`
argv verifies headed/profile ownership; cleanup checks the owned process/profile.
An owned fallback Xvfb uses `-displayfd` rather than a potentially shared fixed
display number; an existing display is never terminated.

The 82-case matrix is 41 cases for each presentation adapter. All 68 title-repair
surface/case identities remain, with two inherited indexed-error pending-focus
assertions corrected to the listed row. Their old bytes and the contract-correct
behavioral red are retained under the correctness-repair evidence root. The
quarantine case retains its timeout/Save/zero-new-generation assertions but now
requires the enabled explicit status route instead of a permanently disabled
Generate. Seven additions per adapter cover indexed existing/pending focus with
real click/Enter, exact payloads, correction/removal and late cross-owner error;
same-draft permit recovery with two separate Generate actions and original adapter;
owner/source/remount late-status fences; timed-out discovery versus a later check;
and stale malformed output classification. Existing all-field/change-back cases
also assert the polite stale-output notice, atomic retention, no field association
or focus hijack, action/edit clearing and absence on cancelled/old-owner results.

The historical 40
first-build and 58 tag-repair cases, with exact source/results, remain frozen in
their original evidence roots. Lifecycle/Save/provenance/error safety semantics
remain. The rejected JSON UI expectations use ordinary entry equivalents.
Specifically, `invalid title and tag syntax cannot Save or silently normalize`
first became `invalid title blocks Save; punctuation tags reach authoritative
validation unchanged` in the tag repair. Its title-disabled assertions were
inherited contract drift: generation-api.md31 forbids frontend policy rejection
and desktop-api.md90/102 requires authoritative validation and corrective focus.
The title repair preserves the punctuation-tag case and replaces the wrong title
expectations with five initial-title cases per adapter: empty, whitespace-only,
161 characters, leading space and trailing space. A real headful behavioral red
first demonstrated the existing disabled Save after a successful valid precondition.
Each replacement case establishes valid Save, exercises exact complete requests
on both click and keyboard Enter against a configured `metadata_invalid` envelope,
asserts fixed copy/association/focus/byte retention, then explicitly corrects the
title and saves without Generate. `titleReceipts` retain observed requests and
error/focus receipts. Fixture `saves` records attempts, including rejected ones;
it is never a durable-write receipt. The configured errors exercise the real
adapter/error-mapper seam but are not an implementation or qualification of
Unicode-14 server validation. A future authenticated adapter must reject invalid
metadata before admission/publication; this fixture performs no durable writes.

`malformed tag edit fences generation and remains visible` becomes unfinished
ordinary input that still fences a valid response, without a syntax-based Save
block. Other JSON fills/assertions become Enter/edit/remove/list-value assertions.
The old 360px theme case is strengthened to live 1000→320 resize, all visible tag
actions, actual Tab order and asserted visible outlines. Long tag text scrolls
inside its editable row; Ctrl+End verifies access without changing its bytes.

The nine tag-repair additions per adapter cover ordinary Enter/no-submit, pending exact Save,
pending generation protection, whitespace/clear eligibility, listed edits/removal
including empty strings, initial invalid bytes across rejected Saves, and three
tag-specific change-back/removal fencing cases. Light/dark are labelled token
fixtures, **not native theme-settings or OS-signal tests**. Desktop visual footer
order is host-owned and differs from Dashboard/DOM keyboard order. This is not
loader, Electron, installed-plugin, authenticated-service, provider, packaging or
shipping evidence.
