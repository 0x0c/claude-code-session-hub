#!/bin/sh
# Double-click launcher for macOS Finder: starts the hub server and opens the dashboard.
#
# - If a hub already answers on the port, it only opens the dashboard and exits.
# - Otherwise it runs the server in this Terminal window. Close the window (or press Ctrl-C) to stop it.
#
# Settings come from the environment, with the same defaults the README recommends:
#   HUB_STORE  store directory (default: ~/.session-hub)
#   HUB_URL    the hub's URL; only its port is used here (default: http://127.0.0.1:8765)
#   HUB_TOKEN  when set, the dashboard opens with ?token= once, and the page switches to a cookie

cd "$(dirname "$0")" || exit 1

HUB_STORE="${HUB_STORE:-$HOME/.session-hub}"
export HUB_STORE
PORT="$(printf '%s' "${HUB_URL:-http://127.0.0.1:8765}" | sed -nE 's#^[a-z]+://[^/:]+:([0-9]+).*#\1#p')"
PORT="${PORT:-8765}"
BASE="http://127.0.0.1:$PORT"
PAGE="$BASE/"
[ -n "$HUB_TOKEN" ] && PAGE="$BASE/?token=$HUB_TOKEN"

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
