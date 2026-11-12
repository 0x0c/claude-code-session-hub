"""Collections: an abstraction over where received updates go, how they accumulate, and how they show.

The event store is the single source of truth; a collection is merely a projection over it.
Four parts define a collection, all declarative JSON with no code to add:

    match   which events to collect   {"type": [...], "kind": [...], "tags_any": [...], "session": [...]}
    reduce  how to combine them       {"type": "log" | "latest" | "aggregate", "payload": "finding", "key": [...]}
    view    how to show them          {"type": "cards" | "table", "group_by": "kind", "columns": [...]}
    sinks   where else to write them  [{"type": "markdown" | "jsonl", "path": "knowledge.md"}]

The built-in collection is "knowledge": it aggregates finding events by key and shows cards by kind.
A definition of the same shape in collections.json at the store root adds or overrides a collection.

Reduce types:
    log        list matching events in time order
    latest     keep the newest event per key (for example, the latest PR state per session)
    aggregate  merge events into one item per key: the newest body, the union of tags and scope,
               and every reporter (for example, three sessions that hit the same caveat yield one
               card that says "reported by 3 sessions")
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

BUILTIN: list[dict] = [
    {
        "name": "knowledge",
        # Display strings may be a plain string or a {"en": ..., "ja": ...} map; the dashboard
        # picks the viewer's language, and sinks and the CLI use their own (see localized()).
        "label": {"en": "Knowledge", "ja": "ナレッジ"},
        "description": {"en": "Findings, caveats, and decisions that sub-sessions discovered while working",
                        "ja": "サブセッションが作業中に見つけた知見・注意点・決定事項"},
        "match": {"type": ["finding"]},
        "reduce": {"type": "aggregate", "payload": "finding", "key": ["key|title"]},
        "view": {
            "type": "cards", "group_by": "kind",
            "groups": {"caveat": {"en": "Caveats", "ja": "注意点"},
                       "issue": {"en": "Open issues", "ja": "未解決の問題"},
                       "decision": {"en": "Decisions", "ja": "決定事項"},
                       "howto": {"en": "How-tos", "ja": "手順・ノウハウ"},
                       "insight": {"en": "Insights", "ja": "知見"}},
            "order": ["caveat", "issue", "decision", "howto", "insight"],
        },
        "sinks": [],
    },
]

REDUCERS = ("log", "latest", "aggregate")
DEFAULT_LANG = "ja"  # the CLI's and the sinks' language until a proposal changes it


def localized(value, lang: str = DEFAULT_LANG):
    """Resolve a display string that is either plain or a {"en": ..., "ja": ...} map."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(iter(value.values()), "")
    return value
VIEWS = ("cards", "table")


class CollectionError(ValueError):
    pass


# ---- Loading definitions --------------------------------------------------

def _validate(d: dict) -> dict:
    if not isinstance(d, dict) or not re.match(r"^[a-z0-9_-]{1,40}$", str(d.get("name", ""))):
        raise CollectionError(f"コレクション名が不正です: {d.get('name') if isinstance(d, dict) else d!r}")
    d = {"label": d["name"], "description": "", "match": {}, "sinks": [], **d}
    d["reduce"] = {"type": "log", "payload": None, "key": [], **(d.get("reduce") or {})}
    d["view"] = {"type": "table", **(d.get("view") or {})}
    if d["reduce"]["type"] not in REDUCERS:
        raise CollectionError(f"{d['name']}: reduce.type は {REDUCERS} のいずれかです")
    if d["view"]["type"] not in VIEWS:
        raise CollectionError(f"{d['name']}: view.type は {VIEWS} のいずれかです")
    for sink in d["sinks"]:
        if sink.get("type") not in ("markdown", "jsonl") or not sink.get("path"):
            raise CollectionError(f"{d['name']}: sinks は {{type: markdown|jsonl, path}} です")
    return d


def load_definitions(store_root: Path | None) -> list[dict]:
    defs = {d["name"]: _validate(dict(d)) for d in BUILTIN}
    path = Path(store_root) / "collections.json" if store_root else None
    if path and path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise CollectionError(f"collections.json を読めません: {e}") from e
        for d in user if isinstance(user, list) else user.get("collections", []):
            if d.get("enabled") is False:
                defs.pop(d.get("name"), None)
                continue
            base = defs.get(d.get("name"), {})
            defs[d["name"]] = _validate({**base, **d})
    return list(defs.values())


# ---- Projection -----------------------------------------------------------

def _payload(ev: dict, field: str | None) -> dict:
    if field:
        p = ev.get(field)
        return p if isinstance(p, dict) else {}
    return ev


def _matches(ev: dict, payload: dict, m: dict) -> bool:
    if m.get("type") and ev["type"] not in m["type"]:
        return False
    if m.get("kind") and payload.get("kind") not in m["kind"]:
        return False
    if m.get("session") and ev["session_id"] not in m["session"]:
        return False
    if m.get("tags_any") and not set(payload.get("tags") or []) & set(m["tags_any"]):
        return False
    if m.get("status") and payload.get("status", "active") not in m["status"]:
        return False
    return True


def _norm(v) -> str:
    return re.sub(r"[\s　]+", " ", str(v)).strip().lower()


def _key(ev: dict, payload: dict, spec: list[str]) -> str:
    """Build the key from spec, an array of field names; 'a|b' falls back to b when a is empty."""
    parts = []
    for f in spec or ["id"]:
        val = None
        for alt in f.split("|"):
            val = payload.get(alt) if alt in payload else ev.get(alt)
            if val not in (None, ""):
                break
        parts.append(_norm(val) if val is not None else "")
    return "/".join(parts)


def _source(ev: dict) -> dict:
    return {"session_id": ev["session_id"], "event_id": ev["id"], "ts": ev["ts"],
            "writer": ev.get("writer")}


def project(defn: dict, events: list[dict]) -> list[dict]:
    """Build a collection's items from events in time order."""
    r = defn["reduce"]
    items: dict[str, dict] = {}
    log: list[dict] = []
    for ev in events:
        payload = _payload(ev, r.get("payload"))
        if not _matches(ev, payload, defn.get("match") or {}):
            continue
        data = {k: v for k, v in payload.items() if k not in ("diff", "state_after")}
        if r["type"] == "log":
            log.append({**data, "key": ev["id"], "sources": [_source(ev)],
                        "first_ts": ev["ts"], "last_ts": ev["ts"], "count": 1})
            continue
        key = _key(ev, payload, r.get("key"))
        cur = items.get(key)
        if r["type"] == "latest" or cur is None:
            prev_sources = cur["sources"] if (cur and r["type"] == "aggregate") else []
            items[key] = {**data, "key": key, "sources": prev_sources + [_source(ev)],
                          "first_ts": cur["first_ts"] if cur else ev["ts"], "last_ts": ev["ts"],
                          "count": (cur["count"] + 1) if cur else 1}
            continue
        # aggregate: the newest values overwrite the body and similar fields, tags and scope merge as
        # a union, and the reporter is appended
        merged = {**cur, **{k: v for k, v in data.items() if v not in (None, "", [])}}
        if "tags" in cur or "tags" in data:
            merged["tags"] = sorted(set(cur.get("tags") or []) | set(data.get("tags") or []))
        scopes = set(cur.get("scopes") or ([cur["scope"]] if cur.get("scope") else []))
        if data.get("scope"):
            scopes.add(data["scope"])
        if scopes:
            merged["scopes"] = sorted(scopes)
        merged.update(key=key, sources=cur["sources"] + [_source(ev)], first_ts=cur["first_ts"],
                      last_ts=ev["ts"], count=cur["count"] + 1)
        items[key] = merged
    out = log if r["type"] == "log" else list(items.values())
    for it in out:
        it["reporters"] = sorted({s["session_id"] for s in it["sources"]})
        if it.get("scope") and "scopes" not in it:
            it["scopes"] = [it["scope"]]
    out.sort(key=lambda it: it["last_ts"], reverse=True)
    return out


def project_all(defs: list[dict], events: list[dict]) -> dict:
    out = {}
    for d in defs:
        items = project(d, events)
        out[d["name"]] = {
            "name": d["name"], "label": d["label"], "description": d.get("description", ""),
            "view": d["view"], "reduce": d["reduce"]["type"], "items": items,
            "active": sum(1 for it in items if it.get("status", "active") == "active"),
        }
    return out


# ---- Writing out (sinks) --------------------------------------------------

def render_markdown(col: dict, session_titles: dict[str, str] | None = None,
                    lang: str = DEFAULT_LANG) -> str:
    titles = session_titles or {}
    view = col["view"]
    lines = [f"# {localized(col['label'], lang)}", ""]
    if col.get("description"):
        lines += [localized(col["description"], lang), ""]
    items = [it for it in col["items"] if it.get("status", "active") == "active"]
    group_by = view.get("group_by")
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(str(it.get(group_by, "")) if group_by else "", []).append(it)
    order = view.get("order") or sorted(groups)
    for g in [*order, *[g for g in groups if g not in order]]:
        if g not in groups:
            continue
        if group_by:
            lines += [f"## {localized((view.get('groups') or {}).get(g, g or '-'), lang)}", ""]
        for it in groups[g]:
            lines.append(f"### {it.get('title') or it.get('summary') or it['key']}")
            meta = []
            if it.get("tags"):
                meta.append(" ".join(f"`{t}`" for t in it["tags"]))
            if it.get("scopes"):
                meta.append("対象: " + ", ".join(it["scopes"]))
            who = ", ".join(titles.get(s, s) for s in it["reporters"])
            meta.append(f"報告: {who}（{it['count']} 件、最終 {it['last_ts'][:16].replace('T', ' ')}）")
            lines += ["", " / ".join(meta), ""]
            if it.get("body"):
                lines += [it["body"], ""]
    return "\n".join(lines).rstrip() + "\n"


def write_sinks(defs: list[dict], projected: dict, store_root: Path,
                session_titles: dict[str, str] | None = None) -> list[Path]:
    """Update the defined sinks, rewriting only the files whose content changed."""
    written = []
    root = Path(store_root).resolve()
    for d in defs:
        col = projected.get(d["name"])
        for sink in d.get("sinks") or []:
            path = (root / sink["path"]).resolve()
            if root not in path.parents:  # Never write outside the store
                raise CollectionError(f"sink の path はストアの中を指定してください: {sink['path']}")
            if sink["type"] == "markdown":
                text = render_markdown(col, session_titles, sink.get("lang", DEFAULT_LANG))
            else:
                text = "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in col["items"])
            old = path.read_text(encoding="utf-8") if path.exists() else None
            if old is None or hashlib.sha256(old.encode()).digest() != hashlib.sha256(text.encode()).digest():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                written.append(path)
    return written
