"""Read which sessions the Claude desktop app has archived, and which session started which.

The app keeps one JSON file per session, <root>/<account>/<organization>/local_<id>.json. We read
four of its fields and never write to the directory:

    cliSessionId  the Claude Code session ID, which is also the hub's session ID
    isArchived    whether the user archived the session
    sessionId     the app's own ID of the session, "local_<id>"
    spawnedFrom   for a session started from another one, an object whose sessionId is the app's ID
                  of the session that started it

The format belongs to the app and is undocumented, so anything unexpected counts as "unknown", and
an unknown session is left as it is.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def default_root() -> Path | None:
    """Return the app's session directory, or None when there is nothing to watch.

    HUB_DESKTOP_SESSIONS overrides the location; an empty value or 0 turns watching off.
    """
    value = os.environ.get("HUB_DESKTOP_SESSIONS")
    if value is not None:
        return Path(value).expanduser() if value not in ("", "0") else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
    return None


class DesktopSessions:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self._cache: dict[Path, tuple[tuple, dict | None]] = {}
        self.parents: dict[str, str] = {}  # {session ID: parent's session ID}, as of the last scan

    @staticmethod
    def _parse(path: Path) -> dict | None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        sid, archived = data.get("cliSessionId"), data.get("isArchived")
        if not isinstance(sid, str) or not isinstance(archived, bool):
            return None
        spawned = data.get("spawnedFrom")
        return {"sid": sid, "archived": archived, "app_id": data.get("sessionId"),
                "from": spawned.get("sessionId") if isinstance(spawned, dict) else None}

    def scan(self) -> dict[str, bool]:
        """Return {session ID: archived}. A file is parsed again only after it changes.

        When several app sessions share one Claude Code session, the session counts as archived
        only if the app archived all of them.
        """
        cache, out = {}, {}
        for path in self.root.glob("*/*/local_*.json"):
            old = self._cache.get(path)
            entry = old
            try:
                st = path.stat()
                sig = (st.st_mtime_ns, st.st_size)
                if not old or old[0] != sig:
                    entry = (sig, self._parse(path))
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                pass  # The app may be mid-write: keep the last good value and retry on the next scan
            if not entry:
                continue
            cache[path] = entry
            if entry[1]:
                sid = entry[1]["sid"]
                out[sid] = out.get(sid, True) and entry[1]["archived"]
        self._cache = cache
        self.parents = self._parents([entry[1] for entry in cache.values() if entry[1]])
        return out

    @staticmethod
    def _parents(files: list[dict]) -> dict[str, str]:
        ids = {f["app_id"]: f["sid"] for f in files if isinstance(f["app_id"], str)}
        found: dict[str, set[str]] = {}
        for f in files:
            parent = ids.get(f["from"]) if isinstance(f["from"], str) else None
            if parent and parent != f["sid"]:
                found.setdefault(f["sid"], set()).add(parent)
        # App sessions that share one Claude Code session may disagree; then the parent is unknown
        return {sid: parents.pop() for sid, parents in found.items() if len(parents) == 1}
