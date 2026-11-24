# shellcheck shell=sh
# Sourced by the hooks and by scripts/setup.sh: where gitleaks lives. Not a hook itself.
#
# Every worktree of a clone shares one copy, kept inside the Git folder. The version is part of the
# path, so raising it here makes the setup incomplete until it runs again.
GITLEAKS_VERSION=8.30.1
GITLEAKS="${GITLEAKS:-$(cd "$(git rev-parse --git-common-dir)" && pwd)/session-hub-tools/gitleaks-$GITLEAKS_VERSION}"

# Fail closed: without gitleaks, nothing is checked.
need_gitleaks() {
  [ -x "$GITLEAKS" ] && return 0
  echo "blocked: gitleaks is not set up, so $1 cannot be checked for secrets; run: make setup" >&2
  exit 1
}

# Refuse the commit and say what to do. --redact keeps the secret out of the output.
blocked() {
  echo "commit blocked: gitleaks reported a problem in $1 (see above)." >&2
  echo "Remove the secret. If it is a false positive, add an allowlist to .gitleaks.toml" >&2
  echo "or a 'gitleaks:allow' comment on that line." >&2
  exit 1
}
