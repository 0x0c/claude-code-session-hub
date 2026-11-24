#!/bin/sh
# Prepare a clone for development: check the tools, install gitleaks, and enable the Git hooks.
# Safe to run again; a finished setup returns at once.
#
#   scripts/setup.sh           set up
#   scripts/setup.sh --check   exit 1 and say so when the setup is incomplete; change nothing
#   scripts/setup.sh --guard   the same for a Claude Code PreToolUse hook: exit 2 blocks the tool
set -eu
cd "$(dirname "$0")/.."
. .githooks/gitleaks.sh

# True when core.hooksPath is this repository's own .githooks: the relative path, or an absolute
# path to this checkout's or the main checkout's copy. core.hooksPath is shared by every linked
# worktree, so a setup run in the main checkout may have left an absolute path behind.
own_hooks() {
  [ -n "$1" ] || return 1
  case "$1" in /*) dir="$1" ;; *) dir="$PWD/$1" ;; esac
  dir="$(cd "$dir" 2>/dev/null && pwd -P)" || return 1
  [ "$dir" = "$(pwd -P)/.githooks" ] && return 0
  main="$(cd "$(git rev-parse --git-common-dir)/.." 2>/dev/null && pwd -P)" || return 1
  [ "$dir" = "$main/.githooks" ]
}

is_set_up() {
  own_hooks "$(git config core.hooksPath || true)" && [ -x "$GITLEAKS" ]
}

case "${1:-}" in
  --check | --guard)
    is_set_up && exit 0
    echo "This clone is not set up. Run 'make setup' before you work on it." >&2
    [ "$1" = --guard ] && exit 2
    exit 1
    ;;
esac

fail() {
  echo "setup: $*" >&2
  exit 1
}

# Print the checksum of the release archive for a platform. Update with GITLEAKS_VERSION.
checksum() {
  case "$1" in
    darwin_arm64) echo b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5 ;;
    darwin_x64) echo dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709 ;;
    linux_arm64) echo e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080 ;;
    linux_x64) echo 551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb ;;
    *) fail "no pinned gitleaks for $1" ;;
  esac
}

install_gitleaks() {
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$(uname -m)" in
    arm64 | aarch64) arch=arm64 ;;
    x86_64 | amd64) arch=x64 ;;
    *) fail "no pinned gitleaks for $(uname -m)" ;;
  esac
  want="$(checksum "${os}_$arch")"
  base="${GITLEAKS_BASE_URL:-https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS_VERSION}"
  mkdir -p "$(dirname "$GITLEAKS")"
  # Build next to the target, so that the final move is atomic when two sessions run at once.
  tmp="$(mktemp -d "$GITLEAKS.XXXXXX")"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL --retry 3 --connect-timeout 10 --max-time 90 -o "$tmp/a.tar.gz" \
    "$base/gitleaks_${GITLEAKS_VERSION}_${os}_$arch.tar.gz" || fail "cannot download gitleaks"
  # A release asset is mutable, so the checksum decides what runs.
  got="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$tmp/a.tar.gz")"
  [ "$got" = "$want" ] || fail "the gitleaks download does not match its checksum"
  tar -xzf "$tmp/a.tar.gz" -C "$tmp" gitleaks
  mv -f "$tmp/gitleaks" "$GITLEAKS"
}

for tool in python3 curl tar; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is missing; install it and run 'make setup' again"
done

# Replacing another hooks folder would silently turn its hooks off, so leave that to the person.
current="$(git config core.hooksPath || true)"
if [ -n "$current" ] && ! own_hooks "$current"; then
  fail "core.hooksPath is already $current; to replace it, run: git config core.hooksPath .githooks"
fi

[ -x "$GITLEAKS" ] || install_gitleaks
[ -n "$current" ] || git config core.hooksPath .githooks
is_set_up || fail "the setup is still incomplete"
echo "setup: ready (gitleaks $GITLEAKS_VERSION, Git hooks enabled)"
