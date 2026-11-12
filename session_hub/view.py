"""ダッシュボード / 時系列ビュー向けのデータ組み立て。LLM は使わない。"""

from __future__ import annotations

from datetime import datetime, timezone

from . import collections, schema

STALE_MINUTES = 30

# DESIGN.md §4.3 の並び順
PRIORITY = {
    "needs_human:blocking": 0, "failed": 1, "review_ready": 2, "stale": 3,
    "needs_human": 4, "changes_requested": 5, "blocked": 6, "working": 7,
    "planning": 7, "in_review": 8, "waiting_ci": 8, "queued": 9, "done": 10, "abandoned": 11,
}
ACTIVE_STATES = ("planning", "working")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def session_view(events: list[dict], now: datetime | None = None,
                 stale_minutes: int = STALE_MINUTES) -> tuple[dict, list[dict]]:
    """1 セッション分のイベントから (ステータス, 差分付きイベント列) を作る。"""
    now = now or _now()
    st = schema.empty_status(events[0]["session_id"])
    st["progress"] = schema.task_progress([])
    timeline = []
    for ev in events:
        nxt = schema.apply_event(st, ev)
        nxt["progress"] = schema.task_progress(nxt["tasks"])
        timeline.append({**ev, "diff": schema.diff_status(st, nxt), "state_after": nxt["state"]})
        st = nxt

    st["gate"] = schema.ready_gate(st)
    age_min = (now - schema.parse_ts(st["heartbeat"])).total_seconds() / 60
    st["stale"] = st["state"] in ACTIVE_STATES and age_min >= stale_minutes
    att = st.get("attention") or {}
    if st["stale"]:
        key = "stale"
    elif st["state"] == "needs_human" and att.get("blocking"):
        key = "needs_human:blocking"
    elif st["state"] == "review_ready" and st["gate"]:
        key = "working"  # 自己申告だけでゲート未通過。要対応には上げない
    else:
        key = st["state"]
    st["priority"] = PRIORITY.get(key, 9)
    st["needs_action"] = st["priority"] <= 4
    return st, timeline


def snapshot(all_events: dict[str, list[dict]], now: datetime | None = None,
             defs: list[dict] | None = None) -> dict:
    """ダッシュボード用の全データ。defs はコレクション定義（省略時は組み込みのみ）。"""
    sessions, events = [], []
    for sid, evs in all_events.items():
        if not evs:
            continue
        st, tl = session_view(evs, now)
        sessions.append(st)
        events.extend(tl)
    sessions.sort(key=lambda s: (s["priority"], s["updated_at"] or ""), reverse=False)
    events.sort(key=lambda e: (e["ts"], e["session_id"], e.get("writer") or "", e["seq"]))
    total = {"cost_usd": round(sum((s["usage"].get("cost_usd") or 0) for s in sessions), 4),
             "input": sum((s["usage"].get("input") or 0) for s in sessions),
             "output": sum((s["usage"].get("output") or 0) for s in sessions)}
    defs = defs if defs is not None else collections.load_definitions(None)
    cols = collections.project_all(defs, events)
    return {"generated_at": schema.now_iso(), "sessions": sessions, "events": events, "total": total,
            "collections": cols}


def knowledge_lines(snap: dict, name: str = "knowledge", kinds: list[str] | None = None,
                    tags: list[str] | None = None, scope: str | None = None, limit: int = 30,
                    with_body: bool = False) -> list[str]:
    """コレクションを LLM に渡しやすい短い行にする（新しい子への引き継ぎなど）。"""
    col = snap.get("collections", {}).get(name)
    if not col:
        return []
    out = []
    for it in col["items"]:
        if it.get("status", "active") != "active":
            continue
        if kinds and it.get("kind") not in kinds:
            continue
        if tags and not set(tags) & set(it.get("tags") or []):
            continue
        if scope and not any(scope in s or s in scope for s in it.get("scopes") or []):
            continue
        head = f"[{it.get('kind', '-')}] {it.get('title') or it['key']}"
        extra = []
        if it.get("tags"):
            extra.append("#" + " #".join(it["tags"]))
        if it.get("scopes"):
            extra.append("@" + ",".join(it["scopes"]))
        if it["count"] > 1:
            extra.append(f"x{it['count']}")
        line = head + (f" ({' '.join(extra)})" if extra else "")
        if with_body and it.get("body"):
            line += "\n    " + it["body"].replace("\n", "\n    ")
        out.append(line)
        if len(out) >= limit:
            break
    return out


# ---- テキスト出力（親 LLM / ターミナル向け） -------------------------------

ICON = {"needs_human": "NH", "review_ready": "RR", "failed": "FL", "done": "OK",
        "working": "WK", "planning": "PL", "waiting_ci": "CI", "blocked": "BL",
        "in_review": "IR", "changes_requested": "CR", "queued": "QU", "abandoned": "AB"}


def _ago(ts: str | None, now: datetime) -> str:
    if not ts:
        return "-"
    m = int((now - schema.parse_ts(ts)).total_seconds() // 60)
    return f"{m}m" if m < 120 else f"{m // 60}h"


def attention_lines(snap: dict, now: datetime | None = None) -> list[str]:
    """親が読む最小限の出力。要対応のセッションだけを 1 行ずつ。"""
    now = now or _now()
    out = []
    for s in snap["sessions"]:
        if not s["needs_action"]:
            continue
        code = "ST" if s["stale"] else ICON.get(s["state"], s["state"][:2].upper())
        ref = s.get("task_ref") or ""
        if s["state"] == "needs_human" and s.get("attention"):
            a = s["attention"]
            opts = "|".join(o + ("*" if o == a.get("default") else "") for o in a.get("options") or [])
            detail = f'{a.get("kind")} q={a.get("qid")} "{a.get("question")}"' + (f" [{opts}]" if opts else "")
            out.append(f"{code} {s['session_id']} {ref} {detail} {_ago(a.get('since'), now)}".replace("  ", " "))
        elif s["stale"]:
            out.append(f"{code} {s['session_id']} {ref} {_ago(s['heartbeat'], now)} since heartbeat".replace("  ", " "))
        elif s["state"] == "failed":
            out.append(f"{code} {s['session_id']} {ref} {s.get('last_error') or s.get('summary') or ''}".replace("  ", " ").strip())
        else:
            pr = s.get("pr") or {}
            prs = f"PR#{pr['number']} ci={pr.get('ci', '-')}" if pr.get("number") else ""
            out.append(f"{code} {s['session_id']} {ref} {prs} {s.get('summary') or ''}".replace("  ", " ").strip())
    return out


def timeline_lines(snap: dict, session_id: str | None = None, include_heartbeat: bool = False) -> list[str]:
    out = []
    for e in snap["events"]:
        if session_id and e["session_id"] != session_id:
            continue
        if e["type"] == "heartbeat" and not include_heartbeat:
            continue
        changes = []
        for k, d in e["diff"].items():
            if k in ("state", "phase"):
                changes.append(f"{k}:{d['from']}→{d['to']}")
            elif k == "progress":
                changes.append(f"tasks:{d['to']['done']}/{d['to']['total']}")
        text = (e.get("attention") or {}).get("question") if e["type"] == "ask" else None
        text = text or e.get("value") or e.get("summary") or e.get("note") or ""
        who = e.get("writer") or e.get("actor")
        out.append(f"{e['ts']} {e['session_id']} [{who}] {e['type']:<9} {' '.join(changes)} {text}".rstrip())
    return out
