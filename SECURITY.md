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

## Release checks

Changes that affect profile binding, stored text, filesystem access, or download behavior
require regression tests. A browser check alone is not a security review. Reports are
handled without promising an unsupported response-time SLA.
