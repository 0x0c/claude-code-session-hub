#!/bin/sh
# Run the gate, after a check that the clone is set up: the test suite, the proposal format check, the bilingual-docs check, the acronym
# check, and the secret scan. All five must pass before a push.
set -eu
cd "$(dirname "$0")/.."
scripts/setup.sh --check
python3 -m unittest discover -s tests
python3 scripts/proposals.py lint
python3 scripts/check_docs.py
python3 scripts/acronyms.py
scripts/check_secrets.sh
