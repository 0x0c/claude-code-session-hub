"""デモ用データを作る。

    python3 scripts/demo.py --store /tmp/hub-demo            # 過去 3 時間分の履歴を作成
    HUB_STORE=/tmp/hub-demo python3 -m session_hub serve             # ハブサーバーを起動
    python3 scripts/demo.py --push http://127.0.0.1:8765     # 子セッションのふりをして数秒おきに push

ブラウザで http://127.0.0.1:8765/ を開くと、push が届くたびに即時反映される。
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


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed(store: EventStore) -> None:
    now = datetime.now(timezone.utc)
    t = lambda m: iso(now - timedelta(minutes=m))  # noqa: E731
    A, B, C, D, E = ("session_01RateLimit", "session_02LogFormat", "session_03SearchIdx",
                     "session_04DepsBump", "session_05ImgResize")
    P = "session_00Parent"

    def add(sid, minutes_ago, writer=None, **f):
        store.append(sid, {"ts": t(minutes_ago), **f}, writer=writer)

    # A: 質問して人間待ち
    add(A, 170, type="start", title="認証APIのレート制限", task_ref="#128", parent_id=P, branch="claude/rate-limit",
        state="planning", summary="既存のミドルウェア構成を調査",
        tasks=[{"t": "設計", "s": "doing", "size": "S"}, {"t": "ミドルウェア", "s": "todo", "size": "M"},
               {"t": "テスト", "s": "todo", "size": "M"}, {"t": "ドキュメント", "s": "todo", "size": "S"}])
    add(A, 150, type="report", state="working", phase="implement", summary="Redis のスライディングウィンドウ方式で実装開始",
        next="ミドルウェア本体", tasks=[{"t": "設計", "s": "done", "size": "S"}, {"t": "ミドルウェア", "s": "doing", "size": "M"},
                                       {"t": "テスト", "s": "todo", "size": "M"}, {"t": "ドキュメント", "s": "todo", "size": "S"}])
    add(A, 120, type="heartbeat", actor="hook", usage={"input": 90000, "output": 9000, "cost_usd": 0.8})
    add(A, 38, type="ask", phase="implement", attention={"kind": "decision", "question": "1分あたりのリクエスト上限は?",
        "options": ["60", "120", "300"], "default": "120", "blocking": True})

    # B: レビュー可（ゲート通過）
    add(B, 160, type="start", title="ログ出力の構造化", task_ref="#131", parent_id=P, state="working", phase="implement",
        summary="logger を JSON 出力に置換", tasks=[{"t": "logger置換", "s": "doing", "size": "M"}, {"t": "テスト", "s": "todo", "size": "S"}])
    add(B, 90, type="report", phase="test", summary="既存テストを JSON 形式に追従",
        tasks=[{"t": "logger置換", "s": "done", "size": "M"}, {"t": "テスト", "s": "doing", "size": "S"}])
    add(B, 40, type="pr", actor="script", state="waiting_ci", pr={"number": 45, "ci": "pending"})
    add(B, 22, type="pr", actor="script", pr={"ci": "pass", "mergeable": True, "unresolved_threads": 0})
    add(B, 6, type="ready", summary="CI 緑、自己レビュー済み", ready={"self_review": True, "tests_added": True, "description": True},
        tasks=[{"t": "logger置換", "s": "done", "size": "M"}, {"t": "テスト", "s": "done", "size": "S"}])

    # C: 作業中
    add(C, 130, type="start", title="検索インデックス刷新", task_ref="#140", parent_id=P, state="planning",
        tasks=[{"t": n, "s": "todo", "size": s} for n, s in
               [("スキーマ", "S"), ("バッチ", "L"), ("差分更新", "M"), ("API", "M"), ("テスト", "M")]])
    for i, (m, phase, summ) in enumerate([(110, "implement", "スキーマ定義を追加"), (70, "implement", "バッチ投入を実装中"),
                                          (25, "implement", "差分更新のキュー処理を実装中")]):
        tasks = [{"t": n, "s": ("done" if j < i else "doing" if j == i else "todo"), "size": s}
                 for j, (n, s) in enumerate([("スキーマ", "S"), ("バッチ", "L"), ("差分更新", "M"), ("API", "M"), ("テスト", "M")])]
        add(C, m, type="report", state="working", phase=phase, summary=summ, tasks=tasks)
    add(C, 2, type="heartbeat", actor="hook", usage={"input": 410000, "output": 38000, "cost_usd": 3.1, "context_pct": 62})

    # D: 失敗
    add(D, 100, type="start", title="依存パッケージ更新", parent_id=P, state="working", summary="lockfile 更新")
    add(D, 55, type="fail", last_error="npm ci が ERESOLVE で失敗（peer 依存の衝突）")

    # E: 停滞（heartbeat が古い）
    add(E, 140, type="start", title="画像リサイズ処理", parent_id=P, state="working", summary="sharp への置換",
        tasks=[{"t": "置換", "s": "doing", "size": "M"}, {"t": "テスト", "s": "todo", "size": "M"}])
    add(E, 47, type="report", summary="sharp のビルドを試行中")

    # 作業中に判明した知見・注意点（ナレッジに集約される）
    def learn(sid, minutes_ago, kind, title, body=None, tags=(), scope=None):
        add(sid, minutes_ago, type="finding", finding={"kind": kind, "title": title, "body": body,
                                                       "tags": list(tags), "scope": scope})
    learn(B, 80, "caveat", "CI の Redis は 6.2 で SCAN の順序が本番(7.x)と違う",
          "順序に依存するテストは CI だけ落ちる。テストでは結果をソートして比較する。", ["ci", "redis"], "tests/")
    learn(C, 60, "caveat", "CI の Redis は 6.2 で SCAN の順序が本番(7.x)と違う", None, ["redis"], "search/indexer.py")
    learn(A, 140, "howto", "ローカルで Redis を使うテストは make redis-up が必要",
          "docker compose -f dev/redis.yml up -d と同じ。CI では services で起動済み。", ["redis", "dev"])
    learn(A, 30, "decision", "レート制限はスライディングウィンドウ方式にする",
          "固定ウィンドウは境界でバーストを許すため不採用。", ["api", "rate-limit"], "api/middleware/")
    learn(D, 56, "issue", "peer 依存の衝突で npm ci が通らない",
          "eslint-plugin-x@5 が eslint@9 を要求。他の依存は eslint@8 固定。", ["deps", "npm"], "package.json")
    learn(C, 100, "insight", "検索インデックスの全件再構築は約 40 分かかる",
          "夜間バッチ以外で走らせると API のレイテンシが悪化する。", ["search", "perf"])

    # 親の回答の履歴（過去の質問）
    add(C, 100, type="ask", attention={"kind": "clarification", "question": "既存インデックスは残す?", "options": ["残す", "削除"],
        "default": "残す", "blocking": False})
    qid = store.read(C)[-1]["seq"]
    add(C, 95, writer="parent", type="answer", actor="parent", qid=qid, value="残す")


def live(url: str, interval: float) -> None:
    C = "session_03SearchIdx"
    steps = [
        dict(type="heartbeat", actor="hook", usage={"input": 430000, "output": 40000, "cost_usd": 3.3, "context_pct": 64}),
        dict(type="report", task_updates=["差分更新=done", "テスト=doing"]),
        dict(type="report", summary="差分更新のテストを追加中", phase="test"),
        dict(type="ask", attention={"kind": "decision", "question": "再インデックスを夜間に限定する?", "options": ["する", "しない"],
                                    "default": "する", "blocking": False}),
        dict(type="report", state="working", summary="API 層に取りかかり"),
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
    p.add_argument("--store", help="履歴を作るストア（指定時のみ作成）")
    p.add_argument("--push", metavar="URL", help="ハブサーバーへ定期的に push する")
    p.add_argument("--interval", type=float, default=4.0)
    a = p.parse_args()
    if a.store:
        root = Path(a.store)
        if (root / "events").exists():
            shutil.rmtree(root / "events")
        seed(EventStore(root))
        print(f"seeded {root}")
    if a.push:
        live(a.push.rstrip("/"), a.interval)


if __name__ == "__main__":
    main()
