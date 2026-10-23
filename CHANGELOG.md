# Changelog

Notable user-facing changes are recorded here. Release tags identify published versions;
this file is not a promise of future features.

## Unreleased — 0.1.0

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
