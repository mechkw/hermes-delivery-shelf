# Security policy

## Report privately

Do not put secrets, private paths, file bytes, conversation excerpts, or exploitable proofs in public issues. Use [GitHub private vulnerability reporting](https://github.com/mechkw/hermes-delivery-shelf/security/advisories/new) if it is available. Otherwise email **repobugs@virtuedev.com** with the subject “Delivery Shelf security”.

Include the affected release or commit, Hermes version, operating system, and fictional reproduction steps. Security fixes target the latest published release. No response-time SLA is promised.

## Host and profile boundaries

Delivery Shelf runs with its Hermes host's permissions. It is not a sandbox against other programs under the same operating-system account. Keep native authentication enabled and restrict host access. Profile-local storage can be on a remote backend and is shared by clients of that profile. The plugin does not encrypt its catalog or managed files.

The host binds the backend profile. A query parameter cannot grant access to another home. Native transport, enablement, and lifecycle are host responsibilities, not reasons to expose a separate unauthenticated file API.

## Preserved files and deletion

Explicit saves can copy allowed selected files into managed versions. Saved size and hash are checked on managed reads; an unavailable managed copy is not replaced with changed source bytes. Legacy entries without versions still depend on original files.

Source policy restricts roots, types, size, names, and safe ordinary-file access. Symlinks, hard-linked files, traversal, hidden paths, and sensitive filenames are refused. An allowed filename or extension does not prove content is free of secrets or malicious data. ZIP remains opaque. POSIX safe-open requirements do not imply universal backend OS support.

Archive retains indefinitely. Trash has a 30- or 60-day deadline. Empty Trash starts a separate 60-minute recovery period. Due cleanup permanently deletes managed Shelf copies and catalog records, never original working files. Back up the whole plugin data directory consistently, not only SQLite metadata. Disabling scheduling does not extend recovery or cancel queued purges.

## Explicit model processing

Typed quick Add can generate missing metadata through Hermes's configured structured-model facade. Manual **Generate** returns a draft without saving. Selected file input and bounded source-anchored history can reach the configured provider; its costs and privacy policy apply. Content mode distinguishes history-only drafts from actual file input. Annotations generated from private content can themselves be private.

Advanced `--file` commands use a separate current-agent handoff when metadata is missing. That path uses the agent's existing context and requires supported routing plus explicit gateway-injection permission where applicable. A queued handoff is not a save. There is no background filesystem discovery or separate Shelf model account.

The native text-Add preparation path rejects `HERMES_PLUGIN_HOST_PROCESS=1` before source discovery or metadata inference because that host cannot propagate caller cancellation. Verify refusal against the exact packaged runtime; source inspection is not installed acceptance. Use manual Add and explicit Save where automatic capture is unsupported, and never weaken isolation as a workaround. A mutation already authorized may complete after client cancellation or a failed confirmation.

## First save and version consent

First capture requires a deliberate save request. A concrete version offer refers to one known saved entry and exact newly delivered bytes, including changed bytes at the same path. Unchanged bytes are silent. **Always for this delivery** applies to that entry and approving owner only, not the whole catalog or future first saves. Approval pauses outside Active and can be revoked through **Ask before next version**. No global setting grants standing consent.

Agent guidance is not proof that every model follows consent instructions. Exact write readback is required before confirming success; uncertain outcomes need inspection before retry.

## Telegram boundary

Native panels need their separate profile-local owner policy. Buttons and numbered results bind to owner, chat/topic, session, profile, message, and application lifecycle and expire. Revocation is checked on interaction. Panel text and attachments are visible to the destination chat, not private per-user records inside a group.

SQLite commits and Telegram delivery are not one transaction. An unconfirmed response does not prove a save or attachment was rolled back. Do not automatically retry an ambiguous send. See [Telegram setup and limits](docs/TELEGRAM.md).

## Release checks

Changes to profile binding, provenance, generation input, file access, standing permission, or cleanup require focused regression evidence. Source tests, captured transport, browser checks, installation, and native/live acceptance are separate claims. Do not publish real plugin data, policies, screenshots, or session exports as evidence.
