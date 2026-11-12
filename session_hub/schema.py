"""Schema definitions, validation, and folding for events and statuses.

We compute a status by folding the event sequence in order.
Events are append-only, so they also serve directly as the source data for the timeline view.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

SCHEMA_VERSION = 1

STATES = (
    "queued", "planning", "working", "waiting_ci", "needs_human", "blocked",
    "review_ready", "in_review", "changes_requested", "done", "failed", "abandoned",
)

# Transitions that should wake the parent (DESIGN.md §1.2)
ESCALATE_STATES = ("needs_human", "review_ready", "failed", "done")

EVENT_TYPES = (
    "start",      # session start (the parent may record it)
    "report",     # update of state, phase, or summary
    "ask",        # question to a human or the parent
    "answer",     # answer to a question (parent to child)
    "command",    # instruction from parent to child
    "ready",      # self-report of review readiness
    "pr",         # PR and CI facts (from a hook or script)
    "heartbeat",  # liveness signal and usage (from a hook)
    "done",
    "fail",
    "finding",    # insight, caveat, or similar learned during work (aggregated into collections)
)

ACTORS = ("child", "parent", "hook", "human", "script")
ATTENTION_KINDS = ("decision", "clarification", "credential", "permission", "review", "external")
TASK_STATES = ("todo", "doing", "done", "skip")
TASK_SIZES = {"S": 1, "M": 3, "L": 8}
CONFIDENCE = ("high", "med", "low")
FINDING_KINDS = ("caveat", "insight", "decision", "howto", "issue")
FINDING_STATUS = ("active", "obsolete")

# Character limits for free-text fields
LIMITS = {
    "summary": 80, "next": 80, "note": 200, "question": 200, "last_error": 120,
    "title": 80, "task": 40, "option": 40, "value": 200,
    "body": 600, "tag": 30, "scope": 120, "key": 80,
}


class SchemaError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_after(ts: str) -> str:
    """Return the timestamp one millisecond after ts."""
    from datetime import timedelta
    dt = parse_ts(ts) + timedelta(milliseconds=1)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def clip(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if key == "body":  # Keep line breaks in the body; collapse whitespace within each line
        lines = [" ".join(ln.split()) for ln in str(value).splitlines()]
        value = "\n".join(lines).strip()
        while "\n\n\n" in value:
            value = value.replace("\n\n\n", "\n\n")
    else:
        value = " ".join(str(value).split())
    limit = LIMITS.get(key)
    if limit and len(value) > limit:
        value = value[: limit - 1] + "…"
    return value


def _check_enum(value, allowed, name):
    if value is not None and value not in allowed:
        raise SchemaError(f"invalid {name}={value!r}; choose one of: {', '.join(allowed)}")


def normalize_event(ev: dict) -> dict:
    """Validate an event and return a new dict with text clipped to the limits."""
    ev = copy.deepcopy(ev)
    for key in ("session_id", "seq", "ts", "type"):
        if ev.get(key) in (None, ""):
            raise SchemaError(f"{key} is required")
    ev.setdefault("v", SCHEMA_VERSION)
    ev.setdefault("actor", "child")
    _check_enum(ev["type"], EVENT_TYPES, "type")
    _check_enum(ev["actor"], ACTORS, "actor")
    _check_enum(ev.get("state"), STATES, "state")
    _check_enum(ev.get("confidence"), CONFIDENCE, "confidence")
    parse_ts(ev["ts"])  # Format check
    if not isinstance(ev["seq"], int) or ev["seq"] < 1:
        raise SchemaError("seq must be an integer of 1 or more")

    for key in ("summary", "next", "note", "last_error", "title"):
        if key in ev:
            ev[key] = clip(ev[key], key)

    if "tasks" in ev:
        tasks = []
        for t in ev["tasks"]:
            _check_enum(t.get("s", "todo"), TASK_STATES, "task.s")
            _check_enum(t.get("size", "M"), TASK_SIZES, "task.size")
            tasks.append({"t": clip(t["t"], "task"), "s": t.get("s", "todo"), "size": t.get("size", "M")})
        ev["tasks"] = tasks

    att = ev.get("attention")
    if att:
        _check_enum(att.get("kind"), ATTENTION_KINDS, "attention.kind")
        att["question"] = clip(att.get("question"), "question")
        att["options"] = [clip(o, "option") for o in att.get("options") or []]
        att.setdefault("blocking", True)
        att.setdefault("qid", ev["seq"])

    fnd = ev.get("finding")
    if ev["type"] == "finding":
        if not isinstance(fnd, dict) or not fnd.get("title"):
            raise SchemaError("a finding event needs finding.title")
        _check_enum(fnd.get("kind", "insight"), FINDING_KINDS, "finding.kind")
        _check_enum(fnd.get("status", "active"), FINDING_STATUS, "finding.status")
        tags = fnd.get("tags") or []
        if not isinstance(tags, list):
            raise SchemaError("finding.tags must be an array")
        ev["finding"] = {k: v for k, v in {
            "kind": fnd.get("kind", "insight"),
            "title": clip(fnd["title"], "title"),
            "body": clip(fnd.get("body"), "body"),
            "tags": sorted({clip(str(t).lower(), "tag") for t in tags if str(t).strip()})[:10],
            "scope": clip(fnd.get("scope"), "scope"),
            "key": clip(fnd.get("key"), "key"),
            "status": fnd.get("status", "active"),
        }.items() if v not in (None, "")}

    if ev["type"] == "ask" and not att:
        raise SchemaError("an ask event needs attention")
    if ev["type"] == "answer":
        if "qid" not in ev:
            raise SchemaError("an answer event needs qid")
        ev["value"] = clip(ev.get("value"), "value")
    return ev


def empty_status(session_id: str) -> dict:
    return {
        "v": SCHEMA_VERSION, "session_id": session_id,
        "title": None, "parent_id": None, "task_ref": None, "repo": None, "branch": None,
        "state": "queued", "phase": None, "summary": None, "next": None, "confidence": None,
        "tasks": [], "attention": None, "pr": {}, "ready": {}, "usage": {},
        "last_error": None, "started_at": None, "updated_at": None, "heartbeat": None,
        "event_count": 0,
    }


def apply_event(status: dict, ev: dict) -> dict:
    """Return a new status dict advanced by one event."""
    st = copy.deepcopy(status)
    st["event_count"] += 1
    st["heartbeat"] = ev["ts"]
    if ev["type"] != "heartbeat":
        st["updated_at"] = ev["ts"]
    if st["started_at"] is None:
        st["started_at"] = ev["ts"]

    for key in ("title", "parent_id", "task_ref", "repo", "branch", "phase",
                "summary", "next", "confidence", "last_error"):
        if ev.get(key) is not None:
            st[key] = ev[key]
    if "tasks" in ev:
        st["tasks"] = ev["tasks"]
    for key in ("pr", "ready", "usage"):
        if key in ev:
            st[key] = {**st[key], **ev[key]}

    t = ev["type"]
    if t == "start" and not ev.get("state") and st["state"] == "queued":
        st["state"] = "planning"
    if t == "ask":
        st["attention"] = {**ev["attention"], "since": ev["ts"]}
        st["state"] = ev.get("state") or "needs_human"
    elif t == "answer":
        if st["attention"] and st["attention"].get("qid") == ev["qid"]:
            st["attention"] = None
            if st["state"] == "needs_human":
                st["state"] = "working"
    elif t == "done":
        st["state"] = "done"
        st["attention"] = None
    elif t == "fail":
        st["state"] = "failed"
    elif t == "ready":
        st["state"] = ev.get("state") or "review_ready"
    if ev.get("state") and t not in ("ask", "done", "fail", "ready"):
        st["state"] = ev["state"]
        if ev["state"] != "needs_human":
            st["attention"] = None
    return st


def task_progress(tasks: list[dict]) -> dict:
    done = sum(1 for t in tasks if t["s"] in ("done", "skip"))
    remaining = sum(TASK_SIZES.get(t.get("size", "M"), 3) for t in tasks if t["s"] in ("todo", "doing"))
    return {"done": done, "total": len(tasks), "remaining": remaining}


def fold(events: list[dict]) -> dict:
    """Compute the status from one session's events in time order."""
    if not events:
        raise SchemaError("events is empty")
    st = empty_status(events[0]["session_id"])
    for ev in events:  # The caller sorts events in time order
        st = apply_event(st, ev)
    st["progress"] = task_progress(st["tasks"])
    return st


def diff_status(before: dict, after: dict) -> dict:
    """Return the diff that shows, in the timeline view, what this event changed."""
    keys = ("state", "phase", "summary", "next", "confidence", "attention",
            "pr", "ready", "last_error", "progress")
    out = {}
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b != a:
            out[k] = {"from": b, "to": a}
    return out


def ready_gate_codes(st: dict) -> list[dict]:
    """Apply the review-ready gate (DESIGN.md §4.1) and return the unmet conditions as codes.

    Each item is {"code": ..., "value": ...}. The dashboard localizes the codes; the CLI formats
    them with ready_gate(). An empty list means the gate passed.
    """
    reasons: list[dict] = []
    pr = st.get("pr") or {}
    ready = st.get("ready") or {}
    if not pr.get("number"):
        reasons.append({"code": "no_pr"})
    if pr.get("number") and pr.get("ci") != "pass":
        reasons.append({"code": "ci", "value": pr.get("ci") or "unknown"})
    if pr.get("mergeable") is False:
        reasons.append({"code": "conflict"})
    if (pr.get("unresolved_threads") or 0) > 0:
        reasons.append({"code": "threads", "value": pr["unresolved_threads"]})
    if st.get("attention"):
        reasons.append({"code": "question"})
    for key in ("self_review", "tests_added", "description"):
        if not ready.get(key):
            reasons.append({"code": key})
    left = [t["t"] for t in st.get("tasks") or [] if t["s"] in ("todo", "doing")]
    if left:
        reasons.append({"code": "tasks", "value": left})
    return reasons


_GATE_TEXT = {
    "no_pr": lambda v: "no PR",
    "ci": lambda v: f"CI: {v}",
    "conflict": lambda v: "merge conflict",
    "threads": lambda v: f"{v} open threads",
    "question": lambda v: "unanswered question",
    "self_review": lambda v: "self-review not done",
    "tests_added": lambda v: "tests not added",
    "description": lambda v: "no PR description",
    "tasks": lambda v: "tasks left: " + ", ".join(v[:3]) + ("…" if len(v) > 3 else ""),
}


def ready_gate(st: dict) -> list[str]:
    """Return the unmet gate conditions as the CLI's messages; an empty list means the gate passed."""
    return [_GATE_TEXT[r["code"]](r.get("value")) for r in ready_gate_codes(st)]
