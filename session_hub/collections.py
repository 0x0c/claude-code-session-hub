"""コレクション: 受け取った更新を「どこに・どうためて・どう見せるか」の抽象化。

イベントストアが唯一の正（source of truth）で、コレクションはその上の投影（projection）にすぎない。
1 つのコレクションは次の 4 つで定義する（すべて宣言的な JSON。コードの追加は不要）。

    match   どのイベントを集めるか     {"type": [...], "kind": [...], "tags_any": [...], "session": [...]}
    reduce  どうまとめるか             {"type": "log" | "latest" | "aggregate", "payload": "finding", "key": [...]}
    view    どう見せるか               {"type": "cards" | "table", "group_by": "kind", "columns": [...]}
    sinks   ほかにどこへ書き出すか     [{"type": "markdown" | "jsonl", "path": "knowledge.md"}]

組み込みは「ナレッジ」（finding イベントを key ごとに集約し、種類別のカードで表示）。
ストア直下の collections.json に同じ形式で定義を書くと、追加・上書きできる。

reduce の種類:
    log        一致したイベントを時系列のまま並べる
    latest     key ごとに最新の 1 件だけ残す（例: セッションごとの最新の PR 状態）
    aggregate  key ごとに 1 件へまとめ、本文は最新、tags と scope は和集合、報告元をすべて残す
               （例: 複数セッションが同じ注意点に気づいたら 1 枚のカードに「3 セッションが報告」）
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

BUILTIN: list[dict] = [
    {
        "name": "knowledge",
        "label": "ナレッジ",
        "description": "サブセッションが作業中に見つけた知見・注意点・決定事項",
        "match": {"type": ["finding"]},
        "reduce": {"type": "aggregate", "payload": "finding", "key": ["key|title"]},
        "view": {
            "type": "cards", "group_by": "kind",
            "groups": {"caveat": "注意点", "issue": "未解決の問題", "decision": "決定事項",
                       "howto": "手順・ノウハウ", "insight": "知見"},
            "order": ["caveat", "issue", "decision", "howto", "insight"],
        },
        "sinks": [],
    },
]

REDUCERS = ("log", "latest", "aggregate")
VIEWS = ("cards", "table")


class CollectionError(ValueError):
    pass


# ---- 定義の読み込み --------------------------------------------------------

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


# ---- 投影 -----------------------------------------------------------------

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
    """key 指定: フィールド名の配列。'a|b' は a が空なら b を使う。"""
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
    """時系列順のイベント列から、コレクションの項目一覧を作る。"""
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
        # aggregate: 本文などは最新で上書き、tags / scope は和集合、報告元は追記
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


# ---- 書き出し（sinks） -----------------------------------------------------

def render_markdown(col: dict, session_titles: dict[str, str] | None = None) -> str:
    titles = session_titles or {}
    view = col["view"]
    lines = [f"# {col['label']}", ""]
    if col.get("description"):
        lines += [col["description"], ""]
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
            lines += [f"## {(view.get('groups') or {}).get(g, g or '-')}", ""]
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
    """定義された書き出し先を更新する。内容が変わったファイルだけ書き換える。"""
    written = []
    root = Path(store_root).resolve()
    for d in defs:
        col = projected.get(d["name"])
        for sink in d.get("sinks") or []:
            path = (root / sink["path"]).resolve()
            if root not in path.parents:  # ストアの外には書かない
                raise CollectionError(f"sink の path はストアの中を指定してください: {sink['path']}")
            if sink["type"] == "markdown":
                text = render_markdown(col, session_titles)
            else:
                text = "".join(json.dumps(it, ensure_ascii=False) + "\n" for it in col["items"])
            old = path.read_text(encoding="utf-8") if path.exists() else None
            if old is None or hashlib.sha256(old.encode()).digest() != hashlib.sha256(text.encode()).digest():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                written.append(path)
    return written
