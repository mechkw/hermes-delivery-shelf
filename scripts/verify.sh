#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
: "${TMPDIR:=$HOME/.hermes/cache/scratch}"
export TMPDIR
mkdir -p "$TMPDIR"
"${PYTHON:-python}" -m unittest discover -s tests -p 'test_*.py' -v
"${PYTHON:-python}" tests/native_probe.py
"${PYTHON:-python}" tests/native_contract.py
npm run build
npm run test:browser
