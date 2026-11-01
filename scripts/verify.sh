#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
# Catalog probes spawn children: sys.path edits in parent Python do not propagate.
HERMES_SOURCE="$(cd "${HERMES_SOURCE:-$HOME/.hermes/hermes-agent}" && pwd)"
export HERMES_SOURCE
export PYTHONPATH="$HERMES_SOURCE${PYTHONPATH:+:$PYTHONPATH}"
: "${TMPDIR:=$HOME/.hermes/cache/scratch}"
export TMPDIR
mkdir -p "$TMPDIR"
"${PYTHON:-python}" -m unittest discover -s tests -p 'test_*.py' -v
"${PYTHON:-python}" tests/native_probe.py
"${PYTHON:-python}" tests/native_contract.py
"${PYTHON:-python}" tests/native_generation_lifecycle.py
"${PYTHON:-python}" tests/native_command_discovery.py
"${PYTHON:-python}" tests/native_telegram.py
"${PYTHON:-python}" tests/native_recent_add.py
"${PYTHON:-python}" tests/native_multisurface_add.py
"${PYTHON:-python}" tests/native_downloads.py
"${PYTHON:-python}" tests/native_telegram_lifecycle.py
npm run build
npm run test:browser
