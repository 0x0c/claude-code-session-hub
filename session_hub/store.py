"""Event store.

Layout:
    <store>/events/<session_id>.jsonl            events the child session writes itself
    <store>/events/<session_id>@<writer>.jsonl   events another writer (such as the parent) writes to that session

Each file has exactly one writer, and that writer only appends.
Therefore, sharing <store> through Git as a clone of the `hub/status` branch causes no conflicts
on pull --rebase. seq numbers events per file, and an event ID is `<file name>#<seq>`.
Events within a session sort by (ts, writer, seq).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import schema

SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def default_store() -> Path:
    return Path(os.environ.get("HUB_STORE", ".hub")).expanduser().resolve()


def current_session_id() -> str | None:
    sid = os.environ.get("HUB_SESSION_ID")
    if sid:
        return sid
    remote = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if remote:
        # Normalize a CCR internal ID (cse_...) to the session_... form that get_session takes
        return "session_" + remote[4:] if remote.startswith("cse_") else remote
    return os.environ.get("CLAUDE_CODE_SESSION_ID")


def _check_id(value: str, name: str) -> str:
    if not SAFE_ID.match(value or "") or "@" in value:
        raise schema.SchemaError(f"{name} に使えない文字が含まれています: {value!r}")
    return value


def sort_key(ev: dict) -> tuple:
    return (ev["ts"], ev.get("writer") or "", ev["seq"])


class EventStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root).expanduser() if root else default_store()
        self.events_dir = self.root / "events"

    # ---- Writing -------------------------------------------------------
    def _path(self, session_id: str, writer: str | None) -> Path:
        _check_id(session_id, "session_id")
        if writer:
            _check_id(writer, "writer")
            return self.events_dir / f"{session_id}@{writer}.jsonl"
        return self.events_dir / f"{session_id}.jsonl"

    def _next_ts(self) -> str:
        """Issue a timestamp (milliseconds) that increases monotonically across the whole store.

        Even when several writers (a child and its parent, say) write in the same millisecond,
        the timestamp alone fixes a unique order.
        """
        clock = self.root / ".clock"
        with open(clock, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                last = f.read().strip()
                ts = schema.now_iso()
                if last and ts <= last:
                    ts = schema.iso_after(last)
                f.seek(0)
                f.truncate()
                f.write(ts)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return ts

    def append(self, session_id: str, fields: dict, writer: str | None = None) -> dict:
        """Assign seq and ts, append the event, and return the normalized event.

        Without writer, the event goes to the child session's own file.
        When the parent writes an answer or an instruction, it passes writer="parent" or similar.
        """
        self.events_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(session_id, writer)
        with open(path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                last = 0
                for line in f:
                    try:
                        last = max(last, json.loads(line).get("seq", 0))
                    except (json.JSONDecodeError, AttributeError):
                        continue
                ev = {"session_id": session_id, "seq": last + 1, "ts": self._next_ts(), **fields}
                ev = schema.normalize_event(ev)
                f.seek(0, os.SEEK_END)
                f.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return self._decorate(ev, path)

    # ---- Reading -------------------------------------------------------
    @staticmethod
    def _decorate(ev: dict, path: Path) -> dict:
        stem = path.stem
        ev["writer"] = stem.split("@", 1)[1] if "@" in stem else None
        ev["id"] = f"{stem}#{ev['seq']}"
        return ev

    def _files(self) -> list[Path]:
        if not self.events_dir.exists():
            return []
        return sorted(self.events_dir.glob("*.jsonl"))

    def session_ids(self) -> list[str]:
        return sorted({p.stem.split("@", 1)[0] for p in self._files()})

    def _read_file(self, path: Path) -> list[dict]:
        out, seen = [], set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = schema.normalize_event(json.loads(line))
                except (json.JSONDecodeError, schema.SchemaError, TypeError, AttributeError):
                    continue  # Skip a corrupt or invalid line and keep the rest
                if ev["seq"] in seen:  # Duplicate line from a Git merge
                    continue
                seen.add(ev["seq"])
                out.append(self._decorate(ev, path))
        return out

    def read(self, session_id: str) -> list[dict]:
        _check_id(session_id, "session_id")
        events = []
        for path in self._files():
            if path.stem == session_id or path.stem.startswith(session_id + "@"):
                events.extend(e for e in self._read_file(path) if e["session_id"] == session_id)
        return sorted(events, key=sort_key)

    def read_all(self) -> dict[str, list[dict]]:
        return {sid: self.read(sid) for sid in self.session_ids()}

    def signature(self) -> tuple:
        """Return (name, size, mtime) per file, for change detection."""
        sig = []
        for p in self._files():
            try:
                st = p.stat()
            except FileNotFoundError:
                continue
            sig.append((p.name, st.st_size, st.st_mtime_ns))
        return tuple(sig)

    # ---- Git sync ------------------------------------------------------
    def is_git(self) -> bool:
        return (self.root / ".git").exists()

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.root), *args],
                              capture_output=True, text=True, check=False)

    def pull(self) -> bool:
        if not self.is_git():
            return False
        return self._git("pull", "--rebase", "--quiet").returncode == 0

    def sync(self, message: str = "hub: update", retries: int = 4, backoff: float = 2.0) -> bool:
        """Run commit, pull --rebase, and push; retry a failed push with exponential backoff."""
        if not self.is_git():
            return False
        self._git("add", "events")
        if self._git("diff", "--cached", "--quiet").returncode != 0:
            self._git("commit", "--quiet", "-m", message)
        delay = backoff
        for attempt in range(retries + 1):
            self._git("pull", "--rebase", "--quiet")
            if self._git("push", "--quiet").returncode == 0:
                return True
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
        return False
