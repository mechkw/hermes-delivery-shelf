# Contributing to Delivery Shelf

Small, well-finished improvements are welcome. Start with an issue for a substantial
feature so we can agree on the problem before introducing another setting or dependency.

## What makes a good change

- Solve a specific user problem and keep the common path simple.
- Use Hermes's supported plugin APIs; do not patch the host or scrape its DOM internals.
- Keep Dashboard and Desktop behavior aligned without pretending their SDKs are identical.
- Preserve profile boundaries. Treat a profile or connection switch as a change of context,
  not merely a label changing at the top of the window.
- Keep storage and network behavior explicit. No background collection, analytics, model
  calls, or external services without a separately reviewed product decision.
- Make loading, empty, failure, and successful states useful—not just the populated screenshot.

## Before opening a pull request

1. Follow the development and test commands in the README and technical documentation.
2. Add a regression test for a bug, including the behavior that should remain valid.
3. Exercise changed UI in both hosts, a narrow mobile viewport, and light/dark themes.
4. Check keyboard focus, accessible field names, and destructive-action confirmation.
5. Rebuild any generated frontend artifacts and include the updated outputs.
6. Use fictional files and conversations in tests and screenshots. Keep local state and
   credentials out of the commit.
7. Describe what changed, why, and the commands you actually ran. If a check could not
   run, say which one and why rather than marking it passed.

## Review expectations

Correctness, privacy, readability, and host compatibility matter more than a large feature
list. A readable direct implementation is usually better than a new framework. Keep
unrelated formatting and refactors out of focused fixes. Changes to file access, source
references, authentication assumptions, or profile handling need explicit negative tests.

## Documentation

Write from the reader's perspective. Put the useful answer first, then explain the mechanism.
Use concrete examples, active verbs, and consistent control names. Screenshots should match
current behavior. Do not claim support for platforms or host versions we have not verified.

## License and conduct

Contributions are submitted under the repository's MIT license. Be specific, constructive,
and respectful. Discuss the behavior of the software, not the motives of the contributor.
Security issues belong in the private channel described in [SECURITY.md](SECURITY.md).
