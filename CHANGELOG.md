# Changelog

Release tags identify published versions. Unreleased notes describe source changes, not a publication or deployment receipt.

## Unreleased

- File-backed saves preserve managed copies and immutable versions. Downloads validate the saved size and hash instead of rereading changed originals. Legacy original-file links remain source-dependent until explicitly preserved.
- Native Desktop adds Together, Library, and Gallery browsing, an adjacent Library inspector, multi-file Add delivery, and Add version. Manual deliveries and versions accept up to 32 files. Web Dashboard keeps its own interface.
- Typed `/shelf add` captures the latest recognized file set. `add r1` captures the newest single file; `add rN` captures N distinct files, from 1 through 8. Discovery remains bounded to eligible active-segment `MEDIA:` references, not folders or reconstructed history.
- Quick capture can generate missing metadata through the configured structured-model service, preserving supplied fields. Generation can be disabled for filename-based quick capture. Manual Generate returns a draft only. Advanced `--file` missing-metadata saves retain their separate current-agent handoff.
- Concrete version offers accept Yes, Always for this delivery, or Keep current. Changed bytes at the same path can be offered; unchanged bytes stay silent. Standing consent is entry/owner scoped, pauses outside Active, and is revocable from delivery details or the Library inspector. First saves stay deliberate.
- Approved single-member version replacements retain managed companion files. Manual Add version defines the complete selected set and preserves earlier versions.
- Archive retains indefinitely. Trash supports 30 or 60 days. Empty Trash applies to all Trash and starts a 60-minute recovery window before managed-copy cleanup. Original working files are never deleted.
- Native settings cover browsing, date/time display, metadata generation, context, retention, and cleanup. Managed-payload usage includes all versions and queued purges, not original files or total profile disk usage.
- Allowed file types include Office documents and opaque ZIP attachments under the existing root, size, and safe-file policy.
- Telegram panels provide saved-file and version choices, explicit Add version confirmation, and bounded attachment sending. `/shelf r3` selects the third newest registration's primary file, not three files. Numbered downloads require an acknowledged expiring list.
- Technical, operations, command, generation, Telegram, and security guides now distinguish preserved files from legacy references and source inspection from installed/live acceptance.

The native text-Add preparation path refuses automatic capture inside an isolated plugin host before its discovery or metadata-inference work. Manual Add, optional generation, and explicit Save remain the fallback. This describes the implementation, not a qualified installed cancellation result. No live Telegram or native installation result is asserted here.

## 0.1.0 - 2026-10-23

### Added

- Explicit delivery registration with titles, descriptions, kinds, projects, tags, and
  optional file and source-session references.
- Profile-local SQLite catalog with search, exact filters, pagination, and revision
  checks to prevent silent overwrites.
- Native Dashboard and Desktop pages, built from a shared responsive React view.
- Native `delivery_shelf_register` and `delivery_shelf_search` tools, plus `/shelf` search.
- Optional registered-file downloads and plain-text previews through authenticated
  host routes, with operator-approved roots and descriptor-based path validation.
- Metadata-only removal: source files are never deleted.
- Light/dark presentation, keyboard dialogs, accessible status messages, and layouts
  exercised at phone, tablet, and desktop widths.
- Original featured artwork, fictional-data screenshots, setup instructions, technical
  reference, security policy, and contribution guidance.

### Scope

This initial version is deliberately curated: no automatic folder scanning, transcript
capture, plugin telemetry, or model calls. Session IDs are references, not verified
provenance. Files remain in place; the catalog is not a backup service.

See [compatibility and verification](docs/TECHNICAL.md#compatibility-and-verification)
for the exact test scope and platform boundaries.
