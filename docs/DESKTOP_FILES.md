# Choose a delivered file

In **Saved → Deliverables → Add delivery**, choose a recent conversation, then a
file explicitly delivered in it. Both selectors have search and bounded paging.
They select files, not assistant replies. The normal flow requires no root alias,
filesystem path, or session ID.

**Generate details** optionally drafts Title, Description and Tags. Context offers
5, 10, 20 or 50 preceding logical exchanges; new profiles default to 10. Explicit
changes persist, while opening the editor does not write preferences. Each
generation POST carries the displayed Context as a strict integer preset; the
backend uses that frozen request value, not the shared preference another window
can change. Omitted API Context defaults to 10 independently of preferences. Review/edit
the draft and press **Save delivery**. Generation never saves a card. You can save
without inference or use **More options → Add metadata manually**. Existing and
source-pruned cards remain editable, including metadata-only cards.

Desktop uses artifact-style cards with raster thumbnails, file-type fallbacks,
hover/focus Download, an always-visible Download action, and Chat access. Dashboard
keeps its existing collection presentation with the same cleaned-up editor.

## What the model receives

Nothing is sent to a model until Generate details is pressed. The plugin uses the
host's public, authenticated `ctx.llm.acomplete_structured` auxiliary task
`delivery_shelf_details`; there is no plugin-owned model client, tool loop or
subagent. Minimal reasoning is requested; model capability clamping and normal
host provider fallback still apply. The UI does not automatically retry a draft
POST. Errors leave manual saving available.

The request includes the selected file's name, the exact associated delivery,
its preceding human request, and the selected number of earlier logical exchanges.
It excludes later conversation content. The isolated history adapter handles
native compression lineage, deduplicated copies, BLOB/NULL display identities and
known private/native carriers. It cannot distinguish arbitrary unmarked private
text from ordinary human text. No transcript is archived into the Shelf entry.

Supported content:

| Content | Model input |
| --- | --- |
| UTF-8 `.txt`, `.md`, `.csv` | At most 64 KiB of text; truncation is reported |
| PNG, JPEG, GIF, WebP | At most 4 MiB via the native multimodal contract; requires a vision-capable configured model |
| PDF, ZIP and other allowed formats | Explicitly labelled history/metadata-only fallback; file contents are not read for inference |
| Invalid UTF-8, unsupported image header or oversized image | Labelled history-only fallback |

PDF extraction/OCR is not implemented. ZIP files are not unpacked or executed.
A non-vision model may reject image input; this is an error, not a claim that the
image was read. Generation validates strict title/description/tags output only;
the model cannot choose a file path or source registration.

## Source and file boundaries

Desktop's rendered in-memory Artifacts registry is not a supported backend local
file discovery API. Until such a public source API exists, `dashboard/native_history.py`
is an isolated plugin-owned read-only adapter, derived from Bookmarks
`3f70841a5037c31bfa03234331dc88528c5911e5`. It has no sibling-plugin runtime dependency
and does not construct SessionDB, migrate the source database or materialize
indices. Replace this adapter rather than extending host internals when a public
source API becomes available.

`dashboard/artifact_source.py` recognizes explicit visible assistant `MEDIA:` and
local Markdown delivery links, including sandbox-prefixed links. It excludes tool
outputs, fenced examples, hidden/private blocks and arbitrary filesystem prose.
It scans no directories. Conversation search is bounded to 1,000 recent eligible sessions;
file discovery to 500 eligible assistant rows in the selected session, with a
64 KiB per-row ceiling. The chooser reports its window and unavailable files.
An artifact existing only in an older parent session is not automatically surfaced
as a new child's candidate; choose its original conversation. Once selected,
generation can traverse bounded native logical ancestry. History collection caps
rows and bytes (4,000 rows, 256 KiB history payload), and reports truncation.

Discovery, exact source resolution, source-based registration and generation
share fail-closed native row visibility and conversation provenance gates.
Hidden/synthetic/model-only/reasoning/analysis rows and malformed metadata cannot
expose file choices. Delegated sessions, inherited delegate compression children,
automation and cron are excluded before conversation ordering/windowing, so they
cannot consume the eligible window or leak titles. Provenance follows native
compression/boundary semantics, at most 100 ancestors. Chooser work has the
read-only connection's one-second/two-million-VM-step budget plus a 10,000
candidate-provenance-check ceiling; exhaustion is a source error, not an empty
or silently incomplete list. Only per-session indexed timestamps are consulted
for ordering, never a scan of all message content.

Source selection is profile-bound and revalidated against the exact origin row's
digest plus stable artifact identity. The expected digest is also checked inside
the same read-only transaction that collects the anchor/history, before inference;
a later rejection alone would not prevent sending replacement content.
Existing approved-root/type/size rules and
the descriptor-based file opener are reused; no root or attachment policy is
widened. Changed source references and files changing during reads/inference are
rejected. The thumbnail endpoint uses the same opener and a narrower 4 MiB raster
limit, with no-store headers; object URLs are revoked on replacement/unmount.

The Shelf still stores references, not file bytes. A file changing after a draft
has completed is not a preserved snapshot. Reopening/downloading uses its current
approved file, and deleting a card never deletes that file.

## Verification boundaries

The repository verification runs native cold `serve` startup with a fictional
loopback provider: its first authenticated generation works before any chat or
catalog/discovery request, and native text/image wire inputs are checked. No paid
provider is needed for this test. Browser tests use real native components and
loaders with fictional transport/state boundaries, including 360×640 scrolling,
keyboard saves, stale source/generation fences and Desktop thumbnails/downloads.
These tests do not substitute for installing the newly built bundle in the actual
Electron client. Compare bundle SHA-256, not the unchanged API version, during
client acceptance.
