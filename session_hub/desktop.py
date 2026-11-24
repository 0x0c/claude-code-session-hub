"""Read which sessions the Claude desktop app holds, which it has archived, and which started which.

The app keeps one JSON file per session, <root>/<account>/<organization>/local_<id>.json. We read
five of its fields and never write to the directory:

    cliSessionId    the Claude Code session ID, which is also the hub's session ID
    isArchived      whether the user archived the session
    sessionId       the app's own ID, which its claude:// links take (optional)
    lastActivityAt  when the session was last active (optional)
    spawnedFrom     for a session started from another one, an object whose sessionId is the app's
                    own ID of the session that started it (optional)

The format belongs to the app and is undocumented, so anything unexpected counts as "unknown", and
an unknown session is left as it is.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

APP_ID = re.compile(r"local_[A-Za-z0-9-]{1,64}")


class AppSession(NamedTuple):
    """What the app knows about one Claude Code session."""
    archived: bool
    app_id: str | None = None  # The app session to open; None when all of them are archived
    active: float = 0


class AppFile(NamedTuple):
    """What one file of the app says."""
    sid: str
    session: AppSession
    app_id: str | None  # Kept for an archived session too: it may be the parent of another one
    origin: str | None  # The app's own ID of the session that started this one


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
        self._cache: dict[Path, tuple[tuple, AppFile | None]] = {}
        self.parents: dict[str, str] = {}  # {session ID: parent's session ID}, as of the last scan

    @staticmethod
    def _parse(path: Path) -> AppFile | None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        sid, archived = data.get("cliSessionId"), data.get("isArchived")
        if not isinstance(sid, str) or not isinstance(archived, bool):
            return None
        app_id, active, spawned = data.get("sessionId"), data.get("lastActivityAt"), data.get("spawnedFrom")
        origin = spawned.get("sessionId") if isinstance(spawned, dict) else None
        app_id = app_id if isinstance(app_id, str) else None
        linkable = not archived and app_id and APP_ID.fullmatch(app_id)
        session = AppSession(archived, app_id if linkable else None, active if isinstance(active, (int, float)) else 0)
        return AppFile(sid, session, app_id, origin if isinstance(origin, str) else None)

    @staticmethod
    def _merge(a: AppSession, b: AppSession) -> AppSession:
        newest = max((x for x in (a, b) if x.app_id), key=lambda x: (x.active, x.app_id), default=a)
        return newest._replace(archived=a.archived and b.archived)

    def scan(self) -> dict[str, AppSession]:
        """Return {session ID: AppSession}. A file is parsed again only after it changes.

        When several app sessions share one Claude Code session, the session counts as archived
        only if the app archived all of them, and app_id names the latest of the others.
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
                sid, found = entry[1].sid, entry[1].session
                out[sid] = self._merge(out[sid], found) if sid in out else found
        self._cache = cache
        self.parents = self._parents([entry[1] for entry in cache.values() if entry[1]])
        return out

    @staticmethod
    def _parents(files: list[AppFile]) -> dict[str, str]:
        ids = {f.app_id: f.sid for f in files if f.app_id}
        found: dict[str, set[str]] = {}
        for f in files:
            parent = ids.get(f.origin)
            if parent and parent != f.sid:
                found.setdefault(f.sid, set()).add(parent)
        # App sessions that share one Claude Code session may disagree; then the parent is unknown
        return {sid: parents.pop() for sid, parents in found.items() if len(parents) == 1}
