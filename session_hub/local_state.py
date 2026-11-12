"""Small local state on the child-session side (the last reported state, task ID-to-name map, and so on).

In push mode the store is remote. We record each send here so that a hook can tell what it
last reported without a network call.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _path(sid: str) -> Path:
    base = Path(os.environ.get("HUB_STATE_DIR", Path.home() / ".cache" / "session-hub"))
    return base / f"state-{sid}.json"


def load(sid: str) -> dict:
    try:
        return json.loads(_path(sid).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(sid: str, st: dict) -> None:
    p = _path(sid)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def note(sid: str, fields: dict, res: dict | None) -> None:
    """Record that this session sent an event (or queued it in the outbox)."""
    st = load(sid)
    if fields.get("actor", "child") == "child":
        st["started"] = True
    if res and res.get("status"):
        st["state"] = res["status"]["state"]
    elif fields.get("type") in ("done", "fail", "ask", "ready"):
        st["state"] = {"done": "done", "fail": "failed", "ask": "needs_human", "ready": "review_ready"}[fields["type"]]
    elif fields.get("state"):
        st["state"] = fields["state"]
    elif fields.get("type") == "start":
        st["state"] = "planning"
    save(sid, st)


def map_task(sid: str, task_id: str, name: str) -> None:
    st = load(sid)
    st.setdefault("tasks", {})[task_id] = name
    save(sid, st)


def task_name(sid: str, task_id: str) -> str | None:
    return load(sid).get("tasks", {}).get(task_id)
