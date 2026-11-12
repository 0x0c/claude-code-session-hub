#!/bin/sh
# Run the gate: the test suite, the proposal format check, and the bilingual-docs check.
# All three must pass before a push.
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests
python3 scripts/proposals.py lint
python3 scripts/check_docs.py
