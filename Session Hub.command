#!/bin/sh
# Double-click launcher for macOS Finder: starts the hub server and opens the dashboard.
#
# - If a hub already answers on the port, it only opens the dashboard and exits.
# - Otherwise it runs the server in this Terminal window. Close the window (or press Ctrl-C) to stop it.
#
# A Finder double-click does not see the "env" block of ~/.claude/settings.json, which reaches
# Claude Code sessions only. So each setting below comes from the shell environment first, then from
# that "env" block, so the server uses the same store and port as the sessions, then from the default:
#   HUB_STORE  store directory (default: ~/.session-hub)
#   HUB_URL    the hub's URL; only its port is used here (default: http://127.0.0.1:8765)
#   HUB_TOKEN  when set, the dashboard opens with ?token= once, and the page switches to a cookie

cd "$(dirname "$0")" || exit 1

# Print the value of one key in the "env" block of ~/.claude/settings.json, or nothing.
setting() {
  python3 - "$1" <<'PY' 2>/dev/null
import json, os, sys
try:
    with open(os.path.expanduser("~/.claude/settings.json")) as f:
        value = json.load(f).get("env", {}).get(sys.argv[1])
except (OSError, ValueError, AttributeError):
    value = None
if isinstance(value, str) and value:
    print(os.path.expanduser(value) if sys.argv[1] == "HUB_STORE" else value)
PY
}

[ -n "$HUB_STORE" ] || HUB_STORE="$(setting HUB_STORE)"
[ -n "$HUB_URL" ] || HUB_URL="$(setting HUB_URL)"
[ -n "$HUB_TOKEN" ] || HUB_TOKEN="$(setting HUB_TOKEN)"
[ -n "$HUB_TOKEN" ] && export HUB_TOKEN
HUB_STORE="${HUB_STORE:-$HOME/.session-hub}"
export HUB_STORE
# Parse the port the way the hooks do (urllib), so IPv6 hosts and uppercase schemes work too.
PORT="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlsplit(sys.argv[1]).port or "")' "${HUB_URL:-http://127.0.0.1:8765}" 2>/dev/null)"
PORT="${PORT:-8765}"
BASE="http://127.0.0.1:$PORT"
PAGE="$BASE/"
# Percent-encode the token: the server decodes it with parse_qs, where "+" means a space.
[ -n "$HUB_TOKEN" ] && PAGE="$BASE/?token=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$HUB_TOKEN")"

healthy() { curl -fsS -m 1 "$BASE/healthz" >/dev/null 2>&1; }

if healthy; then
  echo "Session Hub is already running at $BASE/"
  open "$PAGE"
  exit 0
fi

# Open the dashboard once the server answers (give up after about 10 seconds).
(
  i=0
  while [ "$i" -lt 50 ]; do
    if healthy; then open "$PAGE"; exit 0; fi
    sleep 0.2
    i=$((i + 1))
  done
) &

echo "Starting Session Hub (store: $HUB_STORE). Close this window or press Ctrl-C to stop it."
exec bin/session-hub serve --port "$PORT"
