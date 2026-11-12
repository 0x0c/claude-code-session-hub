#!/bin/sh
# Run the gate: the test suite, the proposal format check, the bilingual-docs check, and the
# acronym check. All four must pass before a push.
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests
python3 scripts/proposals.py lint
python3 scripts/check_docs.py
python3 scripts/acronyms.py
