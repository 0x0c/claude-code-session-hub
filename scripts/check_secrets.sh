#!/bin/sh
# Scan every commit reachable from HEAD for secrets, including commits that bypassed the hooks.
set -eu
cd "$(dirname "$0")/.."
. .githooks/gitleaks.sh

need_gitleaks "the history"
# `git log -p` hides what a merge commit itself changes unless --diff-merges says otherwise.
"$GITLEAKS" git --redact --verbose --no-banner --log-level warn --config .gitleaks.toml \
  --log-opts="--diff-merges=first-parent HEAD"
echo "secrets: no leaks found"
