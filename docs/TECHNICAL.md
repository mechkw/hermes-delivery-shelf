# Delivery Shelf technical reference

[README](../README.md) · [Operations](OPERATIONS.md) · [Commands](COMMANDS.md) · [Security](../SECURITY.md)

Delivery Shelf stores deliberate file collections and preserved file versions. The backend owns the catalog, approved-source policy, managed copies, and lifecycle transitions. Native Desktop and web Dashboard use the host's authenticated plugin transport. They do not expose identical interfaces.

## Runtime layout

| Source | Responsibility |
| --- | --- |
| `__init__.py` | Five tools, `/shelf`, generation-task registration, and lifecycle hooks. |
| `agent_quick_add.py`, `recent_artifacts.py` | Explicit recent-command capture and bounded source discovery. |
| `agent_versions.py`, `agent_awareness.py` | Concrete version offers, entry-scoped approval, and relevant saved-delivery context. |
| `telegram_shelf.py` | Optional host-owned panels, file attachments, numbered results, and panel Add. |
| `dashboard/plugin_api.py` | Models, SQLite catalog, authenticated routes, and generation facade. |
| `dashboard/managed_files.py`, `dashboard/provenance.py` | Managed file bytes and per-file/version source records. |
| `dashboard/lifecycle.py`, `dashboard/shelf_settings.py` | Archive, Trash, recovery deadlines, cleanup, and preferences. |
| `ui/NativeShelf.jsx`, `ui/NativeLibrary.jsx` | Native Desktop chooser, details, Together, Library, and Gallery. |
| `ui/Shelf.jsx`, `ui/dashboard.jsx` | Web Dashboard view and adapter. |
| `desktop/plugin.js`, `dashboard/dist/index.js` | Built client bundles. |

Desktop uses `ctx.rest`; Dashboard uses its native authenticated transport. Backend profile binding selects the store. A `profile` query argument acknowledges that binding and cannot switch filesystem homes. A mismatch returns 409.

## Catalog and managed storage

The backend stores data beneath the bound Hermes home:

```text
plugin-data/delivery-shelf/
  shelf.sqlite3
  managed-files/
  agent-links.sqlite3
  allowed-roots.json
  telegram-owners.json
```

Policy and supporting-state files are created only when needed. `shelf.sqlite3` contains entry metadata, versions, provenance, lifecycle state, preferences, and the durable purge queue. `agent-links.sqlite3` contains agent associations, offers, and scoped version permissions.

A file-backed create copies the selected files into a new managed version. Each managed file records its name, size, content hash, media type, and provenance. Managed downloads read those copies, validate size and hash, and never fall back to changed original bytes when a copy is missing or corrupt. Original paths are retained as provenance, not used as managed-download locations.

A legacy entry without versions remains an original-file reference. Its download still requires the source and current source policy. A metadata edit does not freeze that source. An explicit new version creates managed copies; an exact-reference quick Add can also preserve an existing legacy registration. Existing reference-only catalogs are not a retroactive backup of earlier bytes.

SQLite connections are short-lived. Mutations use transactions and revision checks where required. File-preserving writes reserve `BEGIN IMMEDIATE`, stage managed copies, and discard the staged version on transaction failure. There is no transaction spanning SQLite, model processing, and client delivery. An uncertain response requires exact-entry inspection before retry.

## Input models

`EntryInput` accepts:

| Field | Contract |
| --- | --- |
| `title` | Required nonblank text, at most 160 characters; control characters refused. |
| `description` | Text, at most 4,000 characters; default empty. |
| `kind` | `document`, `image`, `report`, `code`, or `other`. |
| `project` | Text, at most 100 characters; control characters refused. |
| `tags` | At most 20 nonblank strings, each at most 40 characters; control characters refused. |
| `file` | Optional primary `FileRef`. |
| `files` | Up to 32 `FileRef` members. The primary file is first in the stored set. |
| `session_id` | Optional source reference, at most 160 letters, digits, `_`, `.`, `:`, or `-`. |
| `source`, `sources` | Optional exact artifact origins, including per-file source selections. |

Unknown fields are rejected. A `FileRef` contains an approved `root` alias and a relative `path`, not a client-supplied absolute path. Manually supplied session metadata is not proof that the file came from that conversation. Source-picker registration resolves the supplied artifact identity before saving. Provenance retains unknown values rather than guessing missing history.

Saved entries add `id`, epoch-second `created` and `updated`, `revision`, `state`, `versions`, and `current_version`. A version has its own ID, increasing number, creation timestamp, and files. Version and file IDs are scoped to their entry when read.

`EntryUpdate` requires the current positive JavaScript-safe `revision`. Metadata-only edits retain existing versions and do not reread unchanged original references. A same-path content change is not detected by a metadata edit; use Add version or an exact approved version offer.

## Tools

Toolset `delivery_shelf` contains:

| Tool | Contract |
| --- | --- |
| `delivery_shelf_register` | Deliberate first capture of selected metadata and optional files. A guarded Add request must carry its exact `request_id` and session. |
| `delivery_shelf_search` | Saved metadata search with `q`, `tag`, `kind`, `project`, `limit`, and `offset`. Default state is Active. |
| `delivery_shelf_update` | Complete metadata replacement using `id` and current `revision`. Not an approval bypass. |
| `delivery_shelf_offer_update` | Exact saved `id`, newly delivered `file`, and optional exact `replaces` member. |
| `delivery_shelf_respond_update` | Exact `offer_id` and `decision` of `yes`, `always`, or `keep`. |

CRUD/search results are JSON strings with `ok` and either `data` or `error`. Version offers add a `status` and `saved` state. An offer is not a save. `unchanged` and `paused` offers do not request a user notification.

A new path in a multi-file version needs the exact saved member it replaces. Approved replacement carries other members forward from managed copies, without requiring their originals. Manual Add version instead defines the entire new file set. Earlier versions remain intact.

Standing approval is scoped to one saved entry and its approving transport owner. It never authorizes first capture or the whole catalog. Offers pause outside Active. Restoring an entry can resume existing permission. The permission API exposes status and revocation, not a grant operation. Native revocation removes all transport-owner grants for that delivery.

## Search and selection

Catalog search matches literal substrings in titles and descriptions. Exact tag filtering uses Unicode casefold. Kind and project filters are exact. Search does not read attachment contents or transcripts. Results sort by last update, then ID. Default page size is 50, maximum 100, and maximum offset is 1,000,000.

Native selection acts on whole deliveries, even when a view shows separate files. Bulk actions accept either explicit IDs or an `EntryFilter`, never both. A filter is evaluated at action time. It is not a frozen snapshot of the count last displayed. Empty Trash in the native UI targets all Trash, independent of visible search or checks.

## Authenticated HTTP API

Mount prefix: `/api/plugins/delivery-shelf`. The host owns authentication and effective enablement. Do not mount these routes as an unauthenticated standalone service.

| Method | Relative route | Result or mutation |
| --- | --- | --- |
| GET | `/status` | Version, profile, root aliases, allowed extensions, and byte limit. |
| GET | `/entries` | Metadata search and pagination; `state` accepts `active`, `archived`, `trash`, `pending_delete`, or `all`. |
| POST | `/entries` | Create metadata and any managed initial version. |
| GET / PUT | `/entries/{id}` | Read, or update using the current revision. |
| DELETE | `/entries/{id}?revision=N` | Move to Trash; returns `files_deleted: false` and the resulting item/state. |
| POST | `/entries/bulk-action` | `archive`, `trash`, `restore`, or `empty_trash` over IDs or a filter. |
| POST | `/entries/{id}/versions` | New managed version from `files`, current `revision`, and optional source or `replace_file`. |
| GET | `/entries/{id}/versions/{version_id}/files/{file_id}` | Exact managed file as `name`, `base64`, and `media_type`. |
| GET | `/entries/{id}/file` | Current primary file; original-source access only for genuine legacy references. |
| GET | `/entries/{id}/file?preview=true` | Plain-text preview, at most 64 KiB, with `truncated`. |
| GET | `/entries/{id}/thumbnail` | Bounded preview for a selected saved file/version where supported. |
| GET / DELETE | `/entries/{id}/version-permission` | Inspect, or revoke, existing standing approval. |
| GET / PUT | `/settings` | Profile-local preferences. |
| GET | `/storage` | Managed-payload usage, including queued purge bytes. |
| POST | `/cleanup` | Explicit due-item cleanup, even with automatic scheduling off. |
| GET | `/sources/sessions` | Bounded recent conversation choices. |
| GET | `/sources/sessions/{session_id}/artifacts` | Bounded delivered-file choices. |
| POST | `/sources/register`, `/sources/register-many` | Resolve selected origins and preserve one file or a file set. |
| POST | `/sources/thumbnail` | Bounded source preview where supported. |
| GET / PUT | `/generation/settings` | `previous_exchanges`, restricted to 5, 10, 20, or 50. |
| POST | `/generation/draft` | Optional structured metadata draft, not a save. |

The internal legacy `Store.delete()` is not the public DELETE route. Public removal uses lifecycle transitions. Do not call internal deletion as a replacement for Trash or cleanup.

## File policy

Default source aliases are `workspace` and `workspaces` beneath the active Hermes home. A valid operator-owned `allowed-roots.json` replaces those defaults. `{}` permits no source-file roots. Malformed policy denies source-file access. See [Approve another root](OPERATIONS.md#approve-another-root).

Files are limited to 10 MiB each. Allowed extensions are `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, and `.zip`. ZIP remains opaque. Text previews are plain text, not executable Markdown or HTML.

Source reads reject traversal, hidden segments, sensitive names, symlinks, hard-linked or non-regular files, and unsafe ancestors. Checks use POSIX descriptor operations, including `dir_fd` and `O_NOFOLLOW`. A supported remote backend is distinct from universal Windows-backend file support. Filename checks do not detect secrets inside an otherwise allowed file.

## Generation and recent Add

Recent command discovery recognizes standalone `MEDIA:` markers in eligible assistant rows within the exact active session segment. It is bounded to 40 replies and 64 KiB per reply. It does not reconstruct old compressed-away deliveries, search folders, or prove successful transport. [Conversation Add](DETERMINISTIC_ADD.md) defines selectors and host limits.

Quick capture generates omitted fields when `generate_metadata` is enabled. Manual native **Generate** drafts metadata from the first selected file. Both use `ctx.llm.acomplete_structured` with task `delivery_shelf_details`, bounded selected-file input, and history anchored at the source response. Provider processing and costs apply. The content mode distinguishes actual file input from history-only context. Generation alone never saves.

Native text-Add preparation rejects an isolated plugin-host process before source discovery or inference. The fallback is manual Add, optional Generate, and explicit Save; isolation stays enabled. This branch must still be qualified against the installed release.

Advanced `--file` saves use a separate current-agent handoff for missing metadata. That path needs supported session routing and explicit gateway-injection permission where required. Accepted handoff is queued work, not a completed save.

## Lifecycle and settings

Archive has no expiration. Trash defaults to 60 days and supports 30 days. Empty Trash moves items to Pending deletion with a separate 60-minute recovery deadline. Restoration is refused after the recorded deadline even if automatic cleanup is disabled. Retention changes recalculate existing Trash deadlines from their trash timestamps.

Due cleanup removes catalog records and queues only managed version IDs for deletion. It never deletes original working paths. Already-queued purge jobs continue even if automatic scheduling is later disabled. Storage usage counts saved version payloads and queued purges, not originals, SQLite files, or preview caches.

Preferences include views, default view, timezone, date format, hour display, quick-capture generation, context count, retention, and automatic cleanup. None grants first-save or global standing consent.

## Compatibility and verification

Source structure, test scripts, and a built bundle are different evidence from installation and native acceptance. Run checks in a disposable development checkout with a separate dependency environment:

```sh
npm ci --ignore-scripts
npx playwright install chromium
export PYTHON=/path/to/development/python
export HERMES_SOURCE=/path/to/hermes-agent
bash scripts/verify.sh
```

The runner includes unit, native fixture, build, and browser checks. It is not a live Telegram or full Electron acceptance receipt. Backend isolation and cancellation, actual saved bytes, paired-plugin load order, remote transport, and native UI require qualification against the exact release artifact. This reference does not certify a minimum host version or successful deployment.
