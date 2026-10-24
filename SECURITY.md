# Security policy

## Report privately

Please do not put secrets, private conversation excerpts, file contents, or exploitable
proofs into a public issue. Use [GitHub private vulnerability reporting](https://github.com/mechkw/hermes-delivery-shelf/security/advisories/new)
as the preferred channel. If you cannot use GitHub private reporting, email
**repobugs@virtuedev.com** with the subject “Delivery Shelf security”.
Include the affected commit or release, Hermes version, operating system, reproduction
steps using fictional data, and expected versus observed behavior.

## Supported versions

Security fixes target the latest published release. Older versions should be upgraded
before reporting a suspected issue, unless the upgrade itself is the issue.

## Trust boundaries

This plugin runs with the permissions of its Hermes host. It is not a sandbox for
other programs running under the same operating-system account. Keep Hermes's native
authentication enabled, restrict host access, and install only plugins you trust.
Do not publish local plugin data, private screenshots, or real session exports in bug reports.

When save metadata is omitted, the command can hand the explicit request to the
current Hermes agent, which processes its existing conversation context using the
host's configured provider. Gateway handoff requires the operator's
`plugins.entries.delivery-shelf.allow_gateway_injection` consent. The plugin has no
separate model client or transcript collector. Queuing is not proof of a successful
save; completion requires tool success and readback. Fully specified saves remain
direct. Treat generated descriptions as private metadata too.

## Telegram callback boundary

Native panels require a separate operator-owned Telegram owner allowlist, re-read
on each interaction. Actions bind to the issuing owner, chat/topic/message, profile,
Application and connection generation; reset/delete/unload expire pending requests.
Add saves require a short-lived request token and matching task-bound session identity.
Derivative offers do not mutate until approval; approval preserves metadata and uses
revision CAS plus exact-ID readback. Same-file edits never send an offer.
See [Telegram setup and limits](docs/TELEGRAM.md), including revocation responsibilities,
hook-driven lifecycle limits, group visibility, bounded memory state, and the disclosed
catalog scanner warning. No live Telegram delivery has been verified for this feature.

## Release checks

Changes that affect profile binding, stored text, filesystem access, or download behavior
require regression tests. A browser check alone is not a security review. Reports are
handled without promising an unsupported response-time SLA.
