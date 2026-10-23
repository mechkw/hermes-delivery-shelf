# Technical guide

[← README](../README.md) · [Operations](OPERATIONS.md) · [Security](../SECURITY.md)

Delivery Shelf is a small catalog, not a filesystem crawler. The backend owns validation,
profile selection, persistence, and file access. The two frontends own presentation and
use their host's authenticated transport.

```text
Hermes tools / /shelf ─────────────────────────────┐
                                                │
Dashboard → native fetchJSON → authenticated API ├→ profile-bound service
Desktop   → native ctx.rest  → authenticated API ┘       │
                                                        ├→ shelf.sqlite3
                                                        └→ approved registered file
                                                           (only on explicit access)
```

## Package map

- `plugin.yaml`, `VERSION`: package identity, capabilities, dependencies, version.
- `__init__.py`: two tools and the `/shelf` command; synchronized lazy service loading.
- `dashboard/plugin_api.py`: input models, catalog, file policy, and FastAPI routes.
- `dashboard/manifest.json`: Dashboard page declaration.
- `ui/Shelf.jsx`, `ui/style.css`: shared React view and scoped styles.
- `ui/dashboard.jsx`: native Dashboard registration and transport adapter.
- `ui/desktop.jsx`: native Desktop route/sidebar and transport adapter.
- `dashboard/dist/index.js`, `desktop/plugin.js`: ready-to-load release bundles.

Dashboard loads an IIFE through its native plugin registry. Desktop loads a self-contained
ES module importing only host-provided `react` and `@hermes/plugin-sdk`. Relative imports
are not needed at runtime. Consumers install the built package; Node is only a development
dependency.

## Registering a delivery

The native `delivery_shelf_register` tool accepts this shape:

```json
{
  "title": "Spring launch report",
  "description": "Approved summary for the launch meeting.",
  "kind": "report",
  "project": "Website",
  "tags": ["launch", "final"],
  "file": {"root": "workspace", "path": "launch/report.pdf"},
  "session_id": "example-session-001"
}
```

This is fictional input. The file must exist under the approved root; omit `file` for a
metadata-only card. Omit `session_id` unless you have an explicit source reference. When
the native host supplies a session ID to the tool handler, the tool can retain that ID
if the input omitted it. It never searches for a likely or most recent conversation.

A session reference is **user/host-supplied metadata, not verified provenance**. Delivery
Shelf neither checks session ownership nor reads transcripts. Its UI copies the ID; it
does not invent a session URL or promise automatic conversation reopening.

### Input rules

- Title: trimmed, required, at most 160 characters.
- Description: at most 4,000 characters.
- Kind: `document`, `image`, `report`, `code`, or `other`.
- Project: trimmed, at most 100 characters.
- Tags: at most 20; each 1–40 printable characters, trimmed, lowercased, deduplicated.
- File: `null` or a root alias and relative path. Never a browser-selected absolute path.
- Session ID: optional, at most 160 characters, limited to letters, digits, `_`, `.`, `:`, and `-`.
- Unknown input keys are rejected.

Saved entries add an opaque ID, Unix-second `created` and `updated` timestamps, and an
integer `revision`. The `kind` label describes a delivery; it does not override the
attachment extension allowlist. A `code` card cannot make an executable downloadable.

## Searching

`delivery_shelf_search` accepts `q`, `tag`, `kind`, `project`, `limit`, and `offset`.
Search is a literal substring match over titles/descriptions, with exact filters for
labels. It does not search attachment contents or conversation transcripts. The default
page has 50 items; the maximum is 100. Offset is bounded at 1,000,000.

Both native tools return a JSON string containing `{ "ok": true, "data": ... }` or
`{ "ok": false, "error": ... }`. `/shelf [search text]` returns up to 20 matching entries.

## HTTP API

The native host mounts the router at `/api/plugins/delivery-shelf`. Use the host SDK;
do not expose the router as a separate unauthenticated service.

| Method | Relative path | Behavior |
|---|---|---|
| GET | `/status` | Version, bound profile name, root aliases, extensions, byte limit; no absolute root paths |
| GET | `/entries` | Search/filter/page; returns `items`, `total`, `limit`, `offset` |
| POST | `/entries` | Validate and create; 201 with saved entry |
| GET | `/entries/{id}` | Read one entry; 404 if absent |
| PUT | `/entries/{id}` | Replace editable fields with current `revision`; return incremented revision |
| DELETE | `/entries/{id}?revision=N` | Delete catalog metadata only; `files_deleted: false` |
| GET | `/entries/{id}/file?preview=true` | Plain-text preview with `text` and `truncated` |
| GET | `/entries/{id}/file` | JSON containing `name`, `base64`, and octet-stream `media_type` |

An optional `profile` query argument acknowledges the **already-bound host profile**.
It cannot select arbitrary profile paths. A mismatch returns 409. A stale revision also
returns 409, so clients must refresh and reconcile rather than overwrite newer changes.

Create is not idempotent: repeating a POST creates another entry. After an ambiguous
network failure, search/read back before retrying. The UI disables duplicate submission
while a request is active, but that is not an exactly-once delivery guarantee.

## Profile and connection isolation

Every request resolves the current home through Hermes's `get_hermes_home()` context.
The service does not retain a global catalog created at import time. Data lives under
`<bound home>/plugin-data/delivery-shelf/shelf.sqlite3`.

Desktop fences requests and completions against profile, connection, and plugin disposal.
Dashboard captures its bundle's profile and rejects completions from a removed bundle.
Disposed views do not issue follow-up mutation verification through a newly rebound
transport. If the host cannot bind the requested profile, the plugin refuses the mismatch;
it does not treat a query string as authorization to switch profiles.

SQLite operations use short-lived connections, transactions, revision checks, a 10-second
busy timeout, and DELETE journaling. SQLite JSON1 is required. Plugin storage is separate
from replaceable package code. This is profile separation within Hermes, not a sandbox
against other software running as the same operating-system user.

## Registered-file security

[Operations](OPERATIONS.md#approve-another-root) explains the operator-owned root policy.
A root allowlist is only the first check:

1. Validate the registered relative path, alias, extension, and filename components.
2. Open each directory component from the filesystem root using descriptors and
   no-follow semantics; reject symlink ancestors as well as symlink final files.
3. Require an ordinary, single-link file and enforce the size bound.
4. Read through the retained descriptor rather than re-opening an unchecked path.
5. Reapply policy on every access, including after an allowed-root change.

Hidden files, traversal, control characters, alternate-stream syntax, obvious sensitive
filename families, databases, active HTML/SVG, executables, devices, directories, FIFOs,
and hard links are refused. Metadata read/search does not read file content.

Downloads are limited to 10 MiB before base64 encoding. Text/Markdown/CSV previews read
at most 64 KiB and render as escaped text. Binary attachments are downloads, not embedded
active documents. A permitted file is a live reference, not an immutable snapshot.

These checks are not content-based secret detection. An innocuously named report can
still contain private information. Approve narrow delivery directories and register
only content you intend to retrieve. On platforms without the required POSIX descriptor
primitives, file access returns 501 rather than weakening the checks; metadata remains
available.

## Build and test

Use Node with npm, a Python environment containing the declared runtime dependencies,
and a Hermes source checkout for native-contract tests. Do not alter a managed Hermes
Python environment with ad-hoc package installation. Use a separate development environment.

```sh
npm ci --ignore-scripts
npx playwright install chromium
# Set these to your development interpreter and Hermes checkout:
export PYTHON=/path/to/python
export HERMES_SOURCE=/path/to/hermes-agent
bash scripts/verify.sh
```

The verification runner executes unit/security tests, native API/auth checks, native
Doctor/catalog validation, builds both adapters, and exercises both loaders in Chromium.
Temporary fictional homes are cleaned on exit. Screenshots remain in `docs/assets/` as
public-safe, fictional-data captures. No production transcript or catalog is needed.

For installation lifecycle checks, use `tests/install_lifecycle.py` with a **disposable**
Hermes checkout beneath `TMPDIR`; native dependency preparation can modify that checkout.
Never point this test at a live Hermes installation. The CI workflow shows the complete
isolated setup. It exercises native install, enable, disable, update while disabled,
and remove, plus the real Desktop copy/update/prune implementation. The catalog is
verified byte-identical across disable, update, and removal.

## Compatibility and verification

Tested with **Hermes v0.22.5**, official commit
`bf0203a794a07aac3ff764972ab9087baa4e4f4e`. The full 21-test runner, native HTTP and
registration checks, both browser-loader suites, and native installation lifecycle
passed on that release. [Continuous verification](https://github.com/mechkw/hermes-delivery-shelf/actions/workflows/verify.yml) reruns the same gates.
The root-policy correction also received an independent focused security review. The
workflow pins the official release and reruns these gates for changes. This does not
establish an older minimum version.

Required host surfaces are native tool/command registration, request-bound home context,
authenticated plugin API mounting, Dashboard React/fetchJSON registration, and Desktop
unified-package loading with `ctx.rest`, route/sidebar contributions, profile/connection
atoms, and disposal hooks. Python dependencies are FastAPI and Pydantic 2.

The complete runner passed after the root-policy review correction:

- 21 unit/security tests, including concurrent profile contexts, revision conflicts,
  and fail-closed handling of dangling policy symlinks and non-regular policy files.
- Native unauthenticated 401, authenticated CRUD/readback, denied source files, served
  release bundle, and disabled-plugin 404 after the router was already mounted.
- Native Doctor: two registered tools, zero findings; catalog validation: 16 checks,
  zero warnings.
- Both native frontend loaders at 360, 768, and 1440 pixels; CRUD, search, preview,
  browser download, keyboard dialogs, error/retry, deletion, and disposal fencing.
- Light → dark → light theme changes, no horizontal overflow, mobile controls at least
  44 pixels high, and measured muted-card text contrast of 4.78:1 light / 7.15:1 dark.

The Desktop harness uses the actual native runtime loader with real React and HTTP,
but doubles SDK state/IPC/UI-kit boundaries. **It is not a full Electron-shell test.**
Full Electron OS-save dialogs, remote/OAuth deployment, Windows/macOS execution, and
out-of-process plugin-host transport are not established by this evidence. Arbitrary
user themes are not covered by the two measured palettes.

## Deliberate boundaries

Version 0.1 does not include automatic capture, generic filesystem browsing, uploads,
transcript indexing, automatic session reopening, bulk actions, import/export, immutable
file copies, or request-ID deduplication. Keeping the scope small makes the privacy and
file-access rules easier to understand and test.
