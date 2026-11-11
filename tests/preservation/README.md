# Unicode-14 metadata contract scope

The reviewed contract in
`docs/egm/reviews/feature-01/integrated-revision-09-ux/generation-api.md`
requires `unicodedata.unidata_version == "14.0.0"`. Do not patch the runtime to
pretend it is supported or remove the production guard.

Run from the repository root with **real Python 3.11**:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/verify-preservation-metadata.py
```

The required `preservation-metadata` workflow job uses Python 3.11, verifies its
real Unicode version, and invokes unittest discovery on this exact directory.
The runner requires all six canonical methods: three supplied-metadata methods
in `test_preservation_metadata.py` and three generated-output parser methods in
`test_generation_contract.py`. All must execute, with zero skips or expected
failures. Missing/empty discovery, an
unexpected manifest, the wrong runtime, or any failure fails the job. The explicit
method manifest is in the runner and must be updated deliberately if this suite
is extended. The original three methods are moved byte-for-byte, including their
existing synthetic *unsupported* version check; supported behavior uses actual
Unicode-14 tables, never patched supported tables.

This directory intentionally has **no `__init__.py`**: root discovery in the
existing Python 3.14.7 host job must not run Unicode-14 success contracts.
At this repair's base (`3e0cc78377f23730874c4ba385c07e4add61017e`), root discovery
had 137 tests: 134 historical host/legacy tests and these three metadata methods.
The repaired Python 3.14 root suite has **135** tests: those unchanged 134 plus
`test_preservation_metadata_runtime.MetadataRuntimeTests.test_actual_unsupported_runtime_refuses_before_metadata_validation`.
That new test exercises the real newer runtime and exact refusal, without mocks.
It skips only on a real Unicode-14 runtime when root tests are run locally; it
must execute (not skip) in the pinned Python 3.14.7 host CI job. Across the two
jobs the initial runtime split had 138 Python methods, not 137 on Python 3.14.
The later parser integration adds its three reviewed methods byte-for-byte to
this supported-runtime directory; the 135-method newer-runtime suite is unchanged.
The parser is a pure output boundary, not provider execution or durable-save proof.

`scripts/verify.sh` also explicitly runs `tests/metadata-errors.test.mjs` (25 Node
unit cases), previously absent from the verify entrypoint. Its existing native,
build, browser and separate install-lifecycle stages remain on Python 3.14.7;
this split does not claim generation/search support on that newer runtime.
Both CI jobs are unconditional gates: neither uses `continue-on-error`, skips,
or a path/event filter. No repository branch-protection settings are changed.
