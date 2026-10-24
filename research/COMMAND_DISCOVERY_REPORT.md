# Delivery Shelf: native command discovery evidence

Implemented concise native descriptions, explicit argument metadata and expanded
non-saving command syntax help. Added `tests/native_command_discovery.py` to
`scripts/verify.sh`, with an optional `--companion` path (not a dependency).

Host: official **v0.22.5**, commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`.
Plugin base commit: `da1cc8dc6923bd27f3f76e029dc234b5e4cb5c8b`; hashes below identify tested working sources.

Full `scripts/verify.sh`: **exit 0**, **58 unit tests passed**, native API,
Doctor/catalog, command discovery, builds and Dashboard/Desktop browser suites.
Shelf's separate native PTB/isolated-host probes also passed. Final clean recheck
used independent Python **3.14.7** venvs per repository with its own CI requirements,
user site disabled, fictional homes and no incoming `PYTHONPATH`. The revised
script resolves/exports `HERMES_SOURCE` and prepends it to `PYTHONPATH`, including
catalog child processes. Existing Node dependencies/Chromium cache were reused.
Both catalogs passed **16 checks**; Shelf retains its disclosed session-accessor
scanner warning, Bookmarks has zero warnings. This is local execution, not CI status.

## Exact verification results

- Actual native PluginManager loading, registry metadata, canonical Telegram menu,
  native gateway `/help` handler, shared `/commands` renderer and plugin syntax
  dispatch: **PASS**, individually and coinstalled (probe launched from either repo).
- Default cap 60: **60 visible, 10 hidden** individually; **60 visible, 11 hidden**
  coinstalled. Neither plugin is visible at the default cap on this host fixture.
- Cap 3: only `help,new,stop`; **67 hidden** individually / **68 hidden** together.
- `prepend` priority `help,new,stop,<installed plugin commands>` with cap 4 alone /
  5 together: exact priority order retained, full descriptions, **66 hidden**.
  With `append` at the same cap, the plugin commands are displaced. Config bounds
  clamp 0→1 and 999→100; at cap 100 both installed commands appear exactly once.
- Both descriptions fit the host's 40-character plugin menu limit. `args_hint`
  begins with optional `[`; `argument_mode` is explicitly `text`. The host's
  required-leading `<` exclusion therefore does not hide these bare-capable commands.
- **Native global gateway `/help` and `/commands` contain neither plugin command.**
  This is an observed v0.22.5 host gap, not a passing global-help requirement.
  `gateway_help_lines` loops only built-in `COMMAND_REGISTRY`; the executors add
  skills but not registered plugins. Metadata cannot repair this through public
  registration. No help override, core patch, duplicate command or menu publisher.
- `/shelf help` and `/bookmark help` return syntax without session metadata,
  consent, owner files or catalog writes. They explain missing metadata, current
  context, direct saves and group limitations; Shelf includes panel Add and `--file`.
- Forced rediscovery replaces handlers with no duplicate entries; targeted unload
  removes registry/menu entries while retaining a companion. Reload restores them.
  Config disable alone leaves resident entries; forced rediscovery removes them.
- Paired native-loader/browser Saved UI regression: **34/34 passed**. UI source
  and built bundles unchanged. This is not full Electron or live Telegram testing.

## Research and boundaries

Reviewed official plugin documentation at
https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/ and the actual
pinned sources below. Registry/menu/help and lifecycle tests use real host code;
all configs/homes/IDs are fictional. There are no live Bot API calls, credentials,
provider calls, production installs, configuration edits or service restarts.
Existing real-model proof is not rerun or represented as new evidence here.

The host publishes default/private/group scopes after connect and forum parent-chat
scopes lazily. Its language/payload fingerprint invalidates the forum-registration
cache, not Telegram's client cache. Registration and local reload do not prove live
publication. `docs/COMMANDS.md` explains per-profile enablement, `prepend` priority,
cap displacement, narrower chat/language overrides, and the host-help limitation.

**Still required for live activation:** separate authorization to install/enable
in the intended gateway profile, grant only needed injection/owner permissions,
merge menu priorities while preserving safety entries, load/restart resident code
when needed, verify bot identity and applicable scope/language readback, and test
actual inbound commands and save/readback. Global `/help` requires an upstream
host fix; priority/configuration alone cannot resolve it. No commit or push was made.

## Tested plugin source SHA-256

| File | SHA-256 |
|---|---|
| `__init__.py` | `22b0ac6ee49047640d7ce62be35a92746810371e1e4c30259322afc2e77efbfc` |
| `tests/native_command_discovery.py` | `8ee0f434a5ce8223f480abf998b144a2d620a0a36f0ce969be38e9b03ca0f3b4` |
| `scripts/verify.sh` | `173c9de08fd8985c0f14506d9cd31fc1e0298459980b63b012653473c0f5cc21` |

## Inspected host source SHA-256

| Host file | SHA-256 |
|---|---|
| `hermes_cli/plugins.py` | `a1ae6586cb5d968cb1fb6a499960c6a75e078f355ef328b5c906f73ec64aff20` |
| `hermes_cli/commands_platforms.py` | `94e9bae8243ae2214f572d159479c47102857bcaa09c4431a13958b36585ad18` |
| `hermes_cli/commands.py` | `519468ddeccb98d0254f66f838e4d2bd5ac9ca467358f21bc2456f2daa42c19c` |
| `hermes_cli/slash_exec.py` | `49627589b3abd852f9ab20387a424ea96ff2eec0db373caf6657b9262995232a` |
| `gateway/slash_commands.py` | `a6cf0f3942e1c3d1602ad30149c2ac88f1e66ea923ffc0967061ef4cbf03a193` |
| `hermes_cli/plugins_ledger.py` | `07f1834f623e132e80a38fa1caa4a9ed421e8caa91ee2bc092d0a8b306baa1b6` |
| `plugins/platforms/telegram/adapter.py` | `12c04c343b455dd88f4d87680e89c058f7d2e7489170924333ffe8639a3006f8` |
