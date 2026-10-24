# Shelf CI dependency fix

## Result and CI harness resolution

The dependency worker added only `python-telegram-bot==22.8` to `tests/requirements-ci.txt`.
The command-discovery worker subsequently resolved the child-process import issue
below in **both** repositories' `scripts/verify.sh`: resolve and export
`HERMES_SOURCE`, then export `PYTHONPATH="$HERMES_SOURCE${PYTHONPATH:+:$PYTHONPATH}"`.

Final recheck used separate disposable Python 3.14.7 venvs, each installed from
that repository's own CI requirements, user site disabled, fictional homes and a
minimal environment with **no incoming PYTHONPATH**. The actual revised
`scripts/verify.sh` supplied it. Both full scripts exited 0: Shelf 58 tests,
Bookmarks 41 tests, native Doctor/catalog/discovery probes, builds and both
Dashboard/Desktop browser suites. Catalog capability subprocesses succeeded;
Shelf retained only its documented session-accessor warning, Bookmarks had none.
Existing Node dependencies and read-only Chromium cache were reused; this was
not an Actions run. Temporary Python environments were cleaned afterward.

The original dependency-worker investigation below is retained as historical
red/green evidence; its pending-harness caveat is now resolved.
Telegram tests remain mandatory and unchanged. No plugin runtime dependencies,
managed Hermes environments, production configuration or services were changed.

**The requirements fix alone is insufficient for a fresh CI runner:** after it,
`tests/native_contract.py` exposes a separate host-source import issue. The
catalog validator starts a child Python process, which inherits the environment
but not the parent's `sys.path.insert`. With only `HERMES_SOURCE` set, it fails:

```text
FAIL: capability probe: register() raised: No module named 'hermes_constants'
```

Setting `PYTHONPATH` to the selected official host makes the entire verification
pass. The owner of `scripts/verify.sh` or the workflow must propagate that source
path before running probes, for example:

```sh
export PYTHONPATH="${HERMES_SOURCE}${PYTHONPATH:+:$PYTHONPATH}"
```

That harness edit is outside this dependency worker's file ownership and was
not made here. Do not interpret the successful run below as proof that the
unmodified GitHub workflow will pass without this environment fix.

## Evidence and pin rationale

- Failed commit: `da1cc8dc6923bd27f3f76e029dc234b5e4cb5c8b`.
- [GitHub run 40115533386](https://github.com/mechkw/hermes-delivery-shelf/actions/runs/40115533386),
  job `120935914312`. Retrieved actual logs using
  `gh api repos/mechkw/hermes-delivery-shelf/actions/jobs/120935914312/logs`.
  Both `test_telegram` and `test_telegram_review` failed with
  `ModuleNotFoundError: No module named 'telegram'` (37 discovered entries,
  two import errors).
- Official host checkout: tag `v0.22.5`, commit
  `bf0203a794a07aac3ff764972ab9087baa4e4f4e`.
  Its `pyproject.toml` pins `python-telegram-bot[webhooks]==22.8` in both
  `messaging` and `telegram` extras. Read-only installed package inspection also
  returned PTB `22.8`; the isolated run independently confirms this version works.
- Offline tests use actual PTB objects, not a webhook server. Therefore the CI
  pin intentionally omits `[webhooks]` and its Tornado dependency. PTB's required
  `httpx>=0.27,<0.29` and Python 3.14 `httpcore>=1.0.9` are already satisfied by
  the existing exact pins. No additional packages were needed.

## Actual isolated execution

Created a new Python **3.14.7** venv with system site packages disabled. Installed
only the original requirements, reproduced both Telegram import failures, then
installed the updated requirements into that same otherwise untouched venv.
`site.ENABLE_USER_SITE` was false, and PTB imported from that scratch venv.
Execution used `env -i`, fictional `HOME`/`HERMES_HOME`, telemetry disabled,
`PYTHONDONTWRITEBYTECODE=1`, and the official host selected explicitly.

A scratch copy of the working tree avoided concurrent-worker/build conflicts.
It used fresh `npm ci` (zero reported vulnerabilities) and a scratch Chromium
installation; Node **22.22.2**, npm **10.9.7**. GitHub used the same Python version
but Node 22.23.3/npm 10.9.9: this is CI-like Linux verification, not an Actions rerun.
The final snapshot included the other worker's native command-discovery probe.

Actual output, with `PYTHONPATH="$HERMES_SOURCE"`:

```text
python -m pip check:
No broken requirements found.

python -m unittest discover -s tests -p 'test_telegram*.py' -v:
Ran 23 tests in 2.010s
OK

bash scripts/verify.sh: exit 0
Ran 58 tests in 2.884s
OK
DOCTOR: 4 native tools registered; zero errors/warnings; lifecycle hooks and Telegram factory.
VALIDATE: 16 checks passed; one disclosed session-accessor warning; isolation=in_process.
```

The script also passed native HTTP/authentication/command contracts, native
command discovery, real PTB/gateway-dispatch and isolated-host fallback probes,
Dashboard/Desktop builds, and both browser contract suites.

```text
python tests/install_lifecycle.py: exit 0
PASS: native install/enable/disable/update/remove; Desktop copy/update/prune; retained SQLite bytes.
```

Lifecycle verification used the disposable official host beneath `TMPDIR`, and
its own fictional home; its supported installer may bootstrap PM only there.
No live Telegram delivery or Electron application QA is claimed.
Non-fatal output included existing Starlette/httpx deprecation and unclosed
SQLite ResourceWarnings, plus the already disclosed broad catalog scanner
warning for documented session accessors. Tests were not skipped or weakened.

Scratch venv, copied repository, caches and raw local logs were removed after
recording this evidence. The pre-existing official host checkout was retained.
Requirements SHA-256:
`49bed5c4ce22eda1e770e043cfff9edddcdf31ddf6c11a002347485c4cab25d7`.
No commit, push, installation into production, or service restart was performed.
