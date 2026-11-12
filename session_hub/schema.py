"""イベントとステータスのスキーマ定義、検証、畳み込み（fold）。

ステータスは「イベントの列を順に畳み込んだ結果」として求める。
イベントは追記のみ（append-only）なので、そのまま時系列ビューの元データになる。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

SCHEMA_VERSION = 1

STATES = (
    "queued", "planning", "working", "waiting_ci", "needs_human", "blocked",
    "review_ready", "in_review", "changes_requested", "done", "failed", "abandoned",
)

# 親を起こすべき遷移（DESIGN.md §1.2）
ESCALATE_STATES = ("needs_human", "review_ready", "failed", "done")

EVENT_TYPES = (
    "start",      # セッション開始（親が記録することもある）
    "report",     # 状態・作業段階・要約の更新
    "ask",        # 人間/親への質問
    "answer",     # 質問への回答（親→子）
    "command",    # 親→子への指示
    "ready",      # レビュー準備の自己申告
    "pr",         # PR / CI の事実情報（hook・スクリプト）
    "heartbeat",  # 生存通知・usage（hook）
    "done",
    "fail",
    "finding",    # 作業で判明した知見・注意点など（コレクションへ集約される）
)

ACTORS = ("child", "parent", "hook", "human", "script")
ATTENTION_KINDS = ("decision", "clarification", "credential", "permission", "review", "external")
TASK_STATES = ("todo", "doing", "done", "skip")
TASK_SIZES = {"S": 1, "M": 3, "L": 8}
CONFIDENCE = ("high", "med", "low")
FINDING_KINDS = ("caveat", "insight", "decision", "howto", "issue")
FINDING_STATUS = ("active", "obsolete")

# 自由記述の上限文字数
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
    """ts の 1 ミリ秒後。"""
    from datetime import timedelta
    dt = parse_ts(ts) + timedelta(milliseconds=1)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def clip(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if key == "body":  # 本文は改行を残す（行内の空白だけ詰める）
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
        raise SchemaError(f"{name}={value!r} は不正です。候補: {', '.join(allowed)}")


def normalize_event(ev: dict) -> dict:
    """イベントを検証し、文字数を切り詰めた新しい dict を返す。"""
    ev = copy.deepcopy(ev)
    for key in ("session_id", "seq", "ts", "type"):
        if ev.get(key) in (None, ""):
            raise SchemaError(f"{key} は必須です")
    ev.setdefault("v", SCHEMA_VERSION)
    ev.setdefault("actor", "child")
    _check_enum(ev["type"], EVENT_TYPES, "type")
    _check_enum(ev["actor"], ACTORS, "actor")
    _check_enum(ev.get("state"), STATES, "state")
    _check_enum(ev.get("confidence"), CONFIDENCE, "confidence")
    parse_ts(ev["ts"])  # 形式チェック
    if not isinstance(ev["seq"], int) or ev["seq"] < 1:
        raise SchemaError("seq は 1 以上の整数です")

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
            raise SchemaError("finding イベントには finding.title が必要です")
        _check_enum(fnd.get("kind", "insight"), FINDING_KINDS, "finding.kind")
        _check_enum(fnd.get("status", "active"), FINDING_STATUS, "finding.status")
        tags = fnd.get("tags") or []
        if not isinstance(tags, list):
            raise SchemaError("finding.tags は配列です")
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
        raise SchemaError("ask イベントには attention が必要です")
    if ev["type"] == "answer":
        if "qid" not in ev:
            raise SchemaError("answer イベントには qid が必要です")
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
    """1 イベント分ステータスを進めた新しい dict を返す。"""
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
    """1 セッション分のイベント列（時系列順）からステータスを求める。"""
    if not events:
        raise SchemaError("events が空です")
    st = empty_status(events[0]["session_id"])
    for ev in events:  # 呼び出し側で時系列順に並べておく
        st = apply_event(st, ev)
    st["progress"] = task_progress(st["tasks"])
    return st


def diff_status(before: dict, after: dict) -> dict:
    """時系列ビューで「このイベントで何が変わったか」を示すための差分。"""
    keys = ("state", "phase", "summary", "next", "confidence", "attention",
            "pr", "ready", "last_error", "progress")
    out = {}
    for k in keys:
        b, a = before.get(k), after.get(k)
        if b != a:
            out[k] = {"from": b, "to": a}
    return out


def ready_gate(st: dict) -> list[str]:
    """レビュー可ゲート（DESIGN.md §4.1）。満たしていない理由の一覧を返す（空なら通過）。"""
    reasons = []
    pr = st.get("pr") or {}
    ready = st.get("ready") or {}
    if not pr.get("number"):
        reasons.append("PRなし")
    if pr.get("number") and pr.get("ci") != "pass":
        reasons.append(f"CI:{pr.get('ci') or '不明'}")
    if pr.get("mergeable") is False:
        reasons.append("コンフリクト")
    if (pr.get("unresolved_threads") or 0) > 0:
        reasons.append(f"未解決の指摘{pr['unresolved_threads']}件")
    if st.get("attention"):
        reasons.append("未回答の質問")
    for key, label in (("self_review", "自己レビュー"), ("tests_added", "テスト"), ("description", "PR説明")):
        if not ready.get(key):
            reasons.append(f"{label}未完")
    left = [t["t"] for t in st.get("tasks") or [] if t["s"] in ("todo", "doing")]
    if left:
        reasons.append("残タスク:" + ",".join(left[:3]) + ("…" if len(left) > 3 else ""))
    return reasons
