#!/bin/sh
# Run the gate: the test suite and the proposal format check. Both must pass before a push.
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests
python3 scripts/proposals.py lint
