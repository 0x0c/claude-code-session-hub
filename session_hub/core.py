"""Shared event recording, used by the CLI (local writes) and the server (push receipt)."""

from __future__ import annotations

from . import schema
from .store import EventStore

PROTOCOL = "HUB/1"


def escalation_line(st: dict) -> str:
    """Build one line the parent can receive as-is through send_message (DESIGN.md §3.3)."""
    if st["state"] == "needs_human" and st.get("attention"):
        a = st["attention"]
        opts = "/".join(a.get("options") or [])
        text = f"q={a['qid']} {a.get('question')}" + (f" ({opts})" if opts else "")
    elif st["state"] == "review_ready":
        pr = st.get("pr") or {}
        text = (f"PR#{pr['number']} ci={pr.get('ci', '-')} " if pr.get("number") else "") + (st.get("summary") or "")
    elif st["state"] == "failed":
        text = st.get("last_error") or st.get("summary") or ""
    else:
        text = st.get("summary") or ""
    return f"[{PROTOCOL}] {st['session_id']} {st['state']} {schema.clip(text, 'note')}".rstrip()


def merge_tasks(current: list[dict], specs: list[str]) -> list[dict]:
    """Update or add tasks from 'name=status[:size]' specs; a status of '-' deletes the task."""
    tasks = [dict(t) for t in current]
    for spec in specs:
        name, _, rest = spec.partition("=")
        state, _, size = rest.partition(":")
        name = name.strip()
        if not name:
            raise schema.SchemaError(f"タスク名がありません: {spec!r}")
        if state == "-":
            tasks = [t for t in tasks if t["t"] != name]
            continue
        found = next((t for t in tasks if t["t"] == name), None)
        if found:
            found["s"] = state or found["s"]
            found["size"] = size or found["size"]
        else:
            tasks.append({"t": name, "s": state or "todo", "size": size or "M"})
    return tasks


def record(store: EventStore, session_id: str, fields: dict, writer: str | None = None) -> dict:
    """Append an event and return the recorded result and whether to notify the parent.

    When fields holds "task_updates" (an array of 'name=status[:size]'), we apply the updates
    to the current task list and record the result as tasks.

    Returns: {"event", "status", "escalate": str|None, "message": str}
    """
    events = store.read(session_id)
    before = schema.fold(events) if events else schema.empty_status(session_id)
    fields = dict(fields)
    updates = fields.pop("task_updates", None)
    if updates:
        if not isinstance(updates, list) or not all(isinstance(u, str) for u in updates):
            raise schema.SchemaError("task_updates は文字列の配列です")
        fields["tasks"] = merge_tasks(before["tasks"], updates)
    ev = store.append(session_id, fields, writer=writer)
    after = schema.fold(store.read(session_id))

    escalate = None
    message = f"ok {ev['id']} state={after['state']}"
    if writer is None and after["state"] in schema.ESCALATE_STATES and (
            after["state"] != before["state"] or ev["type"] == "ask"):
        gate = schema.ready_gate(after) if after["state"] == "review_ready" else []
        if gate:
            message += f"（レビュー条件未達のため親へは送らない: {', '.join(gate)}）"
        else:
            escalate = escalation_line(after)
            message = escalate
    return {"event": ev, "status": after, "escalate": escalate, "message": message}
