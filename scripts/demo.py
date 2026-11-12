"""Generate demo data, in English or Japanese.

    python3 scripts/demo.py --store /tmp/hub-demo [--lang en|ja]   # create three hours of history
    HUB_STORE=/tmp/hub-demo python3 -m session_hub serve             # start the hub server
    python3 scripts/demo.py --push http://127.0.0.1:8765 [--lang ja] # push every few seconds as a child

Open http://127.0.0.1:8765/ in a browser; each push appears there at once. Add ?lang=en or ?lang=ja
to the URL to pick the dashboard's language; pick the demo data's language with --lang.
"""

from __future__ import annotations

import argparse
import random
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from session_hub import client  # noqa: E402
from session_hub.store import EventStore  # noqa: E402

# Every piece of sample text, keyed by a short id, in both languages.
TEXT = {
    "en": {
        "a.title": "Rate limiting for the auth API", "a.s1": "Surveying the existing middleware",
        "a.s2": "Started a Redis sliding-window implementation", "a.next": "The middleware itself",
        "a.q": "Requests per minute limit?",
        "b.title": "Structured log output", "b.s1": "Replacing the logger with JSON output",
        "b.s2": "Updating existing tests to the JSON format", "b.s3": "CI green, self-reviewed",
        "c.title": "Search index overhaul", "c.s1": "Added the schema definition", "c.s2": "Implementing the batch load",
        "c.s3": "Implementing the incremental-update queue",
        "c.q": "Keep the existing index?", "c.keep": "Keep", "c.drop": "Delete",
        "d.title": "Dependency upgrade", "d.s1": "Updating the lockfile",
        "d.err": "npm ci fails with ERESOLVE (peer dependency conflict)",
        "e.title": "Image resizing", "e.s1": "Switching to sharp", "e.s2": "Trying to build sharp",
        "t.design": "Design", "t.mw": "Middleware", "t.tests": "Tests", "t.docs": "Docs", "t.logger": "Replace logger",
        "t.schema": "Schema", "t.batch": "Batch", "t.incr": "Incremental update", "t.api": "API", "t.swap": "Swap library",
        "k.redis": "CI's Redis 6.2 orders SCAN results differently from production (7.x)",
        "k.redis.b": "Tests that depend on the order fail only in CI. Sort the results before comparing.",
        "k.up": "Tests that use Redis locally need make redis-up",
        "k.up.b": "Same as docker compose -f dev/redis.yml up -d. CI starts Redis as a service.",
        "k.sw": "Use a sliding window for rate limiting",
        "k.sw.b": "Rejected the fixed window because it allows bursts at the window boundary.",
        "k.peer": "npm ci fails on a peer dependency conflict",
        "k.peer.b": "eslint-plugin-x@5 requires eslint@9; the other dependencies pin eslint@8.",
        "k.rebuild": "A full rebuild of the search index takes about 40 minutes",
        "k.rebuild.b": "Running it outside the nightly batch slows API responses.",
        "l.s1": "Adding tests for incremental updates", "l.q": "Limit reindexing to the nightly window?",
        "l.yes": "Yes", "l.no": "No", "l.s2": "Starting on the API layer",
    },
    "ja": {
        "a.title": "認証APIのレート制限", "a.s1": "既存のミドルウェア構成を調査",
        "a.s2": "Redis のスライディングウィンドウ方式で実装開始", "a.next": "ミドルウェア本体",
        "a.q": "1分あたりのリクエスト上限は?",
        "b.title": "ログ出力の構造化", "b.s1": "logger を JSON 出力に置換",
        "b.s2": "既存テストを JSON 形式に追従", "b.s3": "CI 緑、自己レビュー済み",
        "c.title": "検索インデックス刷新", "c.s1": "スキーマ定義を追加", "c.s2": "バッチ投入を実装中",
        "c.s3": "差分更新のキュー処理を実装中",
        "c.q": "既存インデックスは残す?", "c.keep": "残す", "c.drop": "削除",
        "d.title": "依存パッケージ更新", "d.s1": "lockfile 更新",
        "d.err": "npm ci が ERESOLVE で失敗（peer 依存の衝突）",
        "e.title": "画像リサイズ処理", "e.s1": "sharp への置換", "e.s2": "sharp のビルドを試行中",
        "t.design": "設計", "t.mw": "ミドルウェア", "t.tests": "テスト", "t.docs": "ドキュメント", "t.logger": "logger置換",
        "t.schema": "スキーマ", "t.batch": "バッチ", "t.incr": "差分更新", "t.api": "API", "t.swap": "置換",
        "k.redis": "CI の Redis は 6.2 で SCAN の順序が本番(7.x)と違う",
        "k.redis.b": "順序に依存するテストは CI だけ落ちる。テストでは結果をソートして比較する。",
        "k.up": "ローカルで Redis を使うテストは make redis-up が必要",
        "k.up.b": "docker compose -f dev/redis.yml up -d と同じ。CI では services で起動済み。",
        "k.sw": "レート制限はスライディングウィンドウ方式にする",
        "k.sw.b": "固定ウィンドウは境界でバーストを許すため不採用。",
        "k.peer": "peer 依存の衝突で npm ci が通らない",
        "k.peer.b": "eslint-plugin-x@5 が eslint@9 を要求。他の依存は eslint@8 固定。",
        "k.rebuild": "検索インデックスの全件再構築は約 40 分かかる",
        "k.rebuild.b": "夜間バッチ以外で走らせると API のレイテンシが悪化する。",
        "l.s1": "差分更新のテストを追加中", "l.q": "再インデックスを夜間に限定する?",
        "l.yes": "する", "l.no": "しない", "l.s2": "API 層に取りかかり",
    },
}


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed(store: EventStore, lang: str = "ja") -> None:
    x = TEXT[lang]
    now = datetime.now(timezone.utc)
    t = lambda m: iso(now - timedelta(minutes=m))  # noqa: E731
    A, B, C, D, E = ("session_01RateLimit", "session_02LogFormat", "session_03SearchIdx",
                     "session_04DepsBump", "session_05ImgResize")
    P = "session_00Parent"

    def add(sid, minutes_ago, writer=None, **f):
        store.append(sid, {"ts": t(minutes_ago), **f}, writer=writer)

    def tasks(*spec):
        return [{"t": x[k], "s": s, "size": size} for k, s, size in spec]

    # A: asked a question and waits for a human
    add(A, 170, type="start", title=x["a.title"], task_ref="#128", parent_id=P, branch="claude/rate-limit",
        state="planning", summary=x["a.s1"],
        tasks=tasks(("t.design", "doing", "S"), ("t.mw", "todo", "M"), ("t.tests", "todo", "M"), ("t.docs", "todo", "S")))
    add(A, 150, type="report", state="working", phase="implement", summary=x["a.s2"], next=x["a.next"],
        tasks=tasks(("t.design", "done", "S"), ("t.mw", "doing", "M"), ("t.tests", "todo", "M"), ("t.docs", "todo", "S")))
    add(A, 120, type="heartbeat", actor="hook", usage={"input": 90000, "output": 9000, "cost_usd": 0.8})
    add(A, 38, type="ask", phase="implement", attention={"kind": "decision", "question": x["a.q"],
        "options": ["60", "120", "300"], "default": "120", "blocking": True})

    # B: review-ready (gate passed)
    add(B, 160, type="start", title=x["b.title"], task_ref="#131", parent_id=P, state="working", phase="implement",
        summary=x["b.s1"], tasks=tasks(("t.logger", "doing", "M"), ("t.tests", "todo", "S")))
    add(B, 90, type="report", phase="test", summary=x["b.s2"],
        tasks=tasks(("t.logger", "done", "M"), ("t.tests", "doing", "S")))
    add(B, 40, type="pr", actor="script", state="waiting_ci", pr={"number": 45, "ci": "pending"})
    add(B, 22, type="pr", actor="script", pr={"ci": "pass", "mergeable": True, "unresolved_threads": 0})
    add(B, 6, type="ready", summary=x["b.s3"], ready={"self_review": True, "tests_added": True, "description": True},
        tasks=tasks(("t.logger", "done", "M"), ("t.tests", "done", "S")))

    # C: working
    plan = [("t.schema", "S"), ("t.batch", "L"), ("t.incr", "M"), ("t.api", "M"), ("t.tests", "M")]
    add(C, 130, type="start", title=x["c.title"], task_ref="#140", parent_id=P, state="planning",
        tasks=tasks(*[(k, "todo", s) for k, s in plan]))
    for i, (m, summ) in enumerate([(110, "c.s1"), (70, "c.s2"), (25, "c.s3")]):
        progress = [(k, "done" if j < i else "doing" if j == i else "todo", s) for j, (k, s) in enumerate(plan)]
        add(C, m, type="report", state="working", phase="implement", summary=x[summ], tasks=tasks(*progress))
    add(C, 2, type="heartbeat", actor="hook", usage={"input": 410000, "output": 38000, "cost_usd": 3.1, "context_pct": 62})

    # D: failed
    add(D, 100, type="start", title=x["d.title"], parent_id=P, state="working", summary=x["d.s1"])
    add(D, 55, type="fail", last_error=x["d.err"])

    # E: stalled (stale heartbeat)
    add(E, 140, type="start", title=x["e.title"], parent_id=P, state="working", summary=x["e.s1"],
        tasks=tasks(("t.swap", "doing", "M"), ("t.tests", "todo", "M")))
    add(E, 47, type="report", summary=x["e.s2"])

    # Findings learned during work (aggregated into the knowledge collection)
    def learn(sid, minutes_ago, kind, key, body=True, tags=(), scope=None):
        add(sid, minutes_ago, type="finding", finding={
            "kind": kind, "title": x[key], "body": x[key + ".b"] if body else None,
            "tags": list(tags), "scope": scope})
    learn(B, 80, "caveat", "k.redis", tags=["ci", "redis"], scope="tests/")
    learn(C, 60, "caveat", "k.redis", body=False, tags=["redis"], scope="search/indexer.py")
    learn(A, 140, "howto", "k.up", tags=["redis", "dev"])
    learn(A, 30, "decision", "k.sw", tags=["api", "rate-limit"], scope="api/middleware/")
    learn(D, 56, "issue", "k.peer", tags=["deps", "npm"], scope="package.json")
    learn(C, 100, "insight", "k.rebuild", tags=["search", "perf"])

    # A question the parent answered earlier
    add(C, 100, type="ask", attention={"kind": "clarification", "question": x["c.q"],
        "options": [x["c.keep"], x["c.drop"]], "default": x["c.keep"], "blocking": False})
    qid = store.read(C)[-1]["seq"]
    add(C, 95, writer="parent", type="answer", actor="parent", qid=qid, value=x["c.keep"])


def live(url: str, interval: float, lang: str = "ja") -> None:
    x = TEXT[lang]
    C = "session_03SearchIdx"
    steps = [
        dict(type="heartbeat", actor="hook", usage={"input": 430000, "output": 40000, "cost_usd": 3.3, "context_pct": 64}),
        dict(type="report", task_updates=[f"{x['t.incr']}=done", f"{x['t.tests']}=doing"]),
        dict(type="report", summary=x["l.s1"], phase="test"),
        dict(type="ask", attention={"kind": "decision", "question": x["l.q"], "options": [x["l.yes"], x["l.no"]],
                                    "default": x["l.yes"], "blocking": False}),
        dict(type="report", state="working", summary=x["l.s2"]),
        dict(type="pr", actor="script", state="waiting_ci", pr={"number": 52, "ci": "pending"}),
    ]
    i = 0
    while True:
        time.sleep(interval + random.random())
        res = client.post(url, {"session_id": C, "fields": steps[i % len(steps)]})
        print("pushed", res["event"]["id"], res["event"]["type"], res["escalate"] or "", flush=True)
        i += 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--store", help="create history in this store (only when given)")
    p.add_argument("--push", metavar="URL", help="push to the hub server every few seconds")
    p.add_argument("--interval", type=float, default=4.0)
    p.add_argument("--lang", choices=sorted(TEXT), default="ja", help="language of the sample data")
    a = p.parse_args()
    if a.store:
        root = Path(a.store)
        if (root / "events").exists():
            shutil.rmtree(root / "events")
        seed(EventStore(root), a.lang)
        print(f"seeded {root} ({a.lang})")
    if a.push:
        live(a.push.rstrip("/"), a.interval, a.lang)


if __name__ == "__main__":
    main()
