"""session-hub コマンド。

子セッション:  session-hub start / report / ask / ready / pr / done / fail
               HUB_URL があればハブサーバーへ push、なければローカルのストアに書く
親セッション:  session-hub attention / log / status / answer / command
人間:          session-hub serve（リアルタイムダッシュボード） / session-hub export（静的 HTML）
hook:          session-hub hook session-start|stop|todo（stdin に hook の JSON）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import client, core, local_state, schema, view
from .store import EventStore, current_session_id
from .usage import usage_from_transcript

PROTOCOL = core.PROTOCOL


def _session(args) -> str:
    sid = args.session or current_session_id()
    if not sid:
        sys.exit("session-hub: セッション ID が分かりません。--session か HUB_SESSION_ID を指定してください")
    return sid


def _record(args, fields: dict, writer: str | None = None, session: str | None = None) -> dict | None:
    """push 先（HUB_URL）があればサーバーへ送り、なければローカルのストアに書く。"""
    sid = session or _session(args)
    url = client.hub_url()
    if url:
        try:
            res = client.push(url, {"session_id": sid, "writer": writer, "fields": fields},
                              token=os.environ.get("HUB_TOKEN"))
        except ValueError as e:
            sys.exit(f"session-hub: {e}")
        if res is None:
            if writer is None:
                local_state.note(sid, fields, None)
            print("session-hub: ハブに届かないため outbox に保存しました（次回送信時に再送）", file=sys.stderr)
            return None
    else:
        store = EventStore(args.store)
        res = core.record(store, sid, fields, writer=writer)
        if not args.no_sync and store.is_git() and not store.sync(f"hub: {sid} {res['event']['type']}"):
            print("hub: 警告: git push に失敗しました（イベントはローカルに保存済み）", file=sys.stderr)
    if writer is None:
        local_state.note(sid, fields, res)
    # 親を起こすべき遷移なら、send_message でそのまま送れる 1 行が message に入っている
    if res["escalate"] or not args.quiet:
        print(res["message"])
    return res


# ---- サブコマンド ---------------------------------------------------------

def cmd_start(a):
    f = {"type": "start", "state": a.state, "title": a.title, "task_ref": a.task_ref,
         "parent_id": a.parent, "repo": a.repo, "branch": a.branch, "summary": a.summary}
    if a.task:
        f["task_updates"] = a.task
    _record(a, {k: v for k, v in f.items() if v is not None})


def cmd_report(a):
    f = {"type": "report", "state": a.state, "phase": a.phase, "summary": a.summary,
         "next": a.next, "confidence": a.confidence, "last_error": a.error, "note": a.note}
    f = {k: v for k, v in f.items() if v is not None}
    if a.task:
        f["task_updates"] = a.task
    if len(f) == 1:
        sys.exit("session-hub report: 更新する項目を 1 つ以上指定してください")
    _record(a, f)


def cmd_ask(a):
    _record(a, {"type": "ask", "attention": {
        "kind": a.kind, "question": a.q, "options": a.opt or [], "default": a.default,
        "blocking": not a.non_blocking}})


def cmd_ready(a):
    ready = {"self_review": a.self_review, "tests_added": a.tests, "description": a.description}
    _record(a, {"type": "ready", "ready": ready, "summary": a.summary} if a.summary
            else {"type": "ready", "ready": ready})


def cmd_pr(a):
    pr = {"number": a.number, "url": a.url, "ci": a.ci, "mergeable": a.mergeable,
          "unresolved_threads": a.threads, "review": a.review}
    f = {"type": "pr", "actor": "script", "pr": {k: v for k, v in pr.items() if v is not None}}
    if a.state:
        f["state"] = a.state
    _record(a, f)


def cmd_done(a):
    _record(a, {k: v for k, v in {"type": "done", "summary": a.summary}.items() if v is not None})


def cmd_fail(a):
    _record(a, {k: v for k, v in {"type": "fail", "last_error": a.error, "summary": a.summary}.items() if v is not None})


def cmd_heartbeat(a):
    usage = {}
    if a.transcript:
        usage = usage_from_transcript(a.transcript)
    elif not sys.stdin.isatty():
        # Claude Code の hook は stdin に {"transcript_path": ...} を渡す
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            if payload.get("transcript_path"):
                usage = usage_from_transcript(payload["transcript_path"])
        except json.JSONDecodeError:
            pass
    if a.cost is not None:
        usage["cost_usd"] = a.cost
    if a.context_pct is not None:
        usage["context_pct"] = a.context_pct
    a.quiet = True
    _record(a, {"type": "heartbeat", "actor": "hook", "usage": usage})


def cmd_answer(a):
    _record(a, {"type": "answer", "actor": "parent", "qid": a.qid, "value": a.value},
            writer=a.writer, session=a.target)
    print(f"[{PROTOCOL}] cmd=answer q={a.qid} v={a.value}")


def cmd_command(a):
    _record(a, {"type": "command", "actor": "parent", "note": f"{a.cmd} " + " ".join(a.arg or [])},
            writer=a.writer, session=a.target)
    print(f"[{PROTOCOL}] cmd={a.cmd} " + " ".join(a.arg or []))


def _snap(a):
    url = client.hub_url()
    if url and not a.store:
        try:
            return client.get_snapshot(url, os.environ.get("HUB_TOKEN"))
        except client.PushError as e:
            sys.exit(f"session-hub: {e}")
    store = EventStore(a.store)
    if getattr(a, "pull", False):
        store.pull()
    return view.snapshot(store.read_all())


def cmd_attention(a):
    lines = view.attention_lines(_snap(a))
    print("\n".join(lines) if lines else "(要対応なし)")


def cmd_status(a):
    snap = _snap(a)
    if a.json:
        print(json.dumps(snap["sessions"], ensure_ascii=False, indent=2))
        return
    for s in snap["sessions"]:
        p = s["progress"]
        code = "ST" if s["stale"] else view.ICON.get(s["state"], "??")
        print(f"{code} {s['session_id']:<28} {p['done']}/{p['total']} {s.get('title') or '':<24} {s.get('summary') or ''}")


def cmd_log(a):
    lines = view.timeline_lines(_snap(a), session_id=a.target, include_heartbeat=a.heartbeat)
    if a.tail:
        lines = lines[-a.tail:]
    print("\n".join(lines))


def cmd_export(a):
    from .server import dashboard_html
    snap = _snap(a)
    data = json.dumps(snap, ensure_ascii=False).replace("</", "<\\/")
    html = dashboard_html().replace("/*__HUB_SNAPSHOT__*/null", data)
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"wrote {a.out}")


def cmd_serve(a):
    from .server import serve
    serve(EventStore(a.store), host=a.host, port=a.port, token=os.environ.get("HUB_TOKEN"),
          watch_files=a.watch_files, pull_every=a.pull_every)


def cmd_hook(a):
    from . import hooks
    hooks.run(a.name)


def cmd_flush(a):
    url = client.hub_url()
    if not url:
        sys.exit("hub: HUB_URL が設定されていません")
    print(f"sent {client.flush(url, os.environ.get('HUB_TOKEN'))}")


# ---- パーサー -------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="session-hub", description="Claude Code セッションの状況共有")
    p.add_argument("--store", help="イベントストアのディレクトリ（既定: $HUB_STORE または .hub）")
    p.add_argument("--session", help="自セッション ID（既定: 環境変数から取得）")
    p.add_argument("--no-sync", action="store_true", help="Git への push をしない")
    p.add_argument("-q", "--quiet", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="セッション開始を記録")
    s.add_argument("--title"); s.add_argument("--task-ref"); s.add_argument("--parent")
    s.add_argument("--repo"); s.add_argument("--branch"); s.add_argument("--summary")
    s.add_argument("--state", default="planning", choices=schema.STATES)
    s.add_argument("--task", action="append", metavar="NAME=STATE[:SIZE]")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("report", help="状態・進捗を更新")
    s.add_argument("--state", choices=schema.STATES); s.add_argument("--phase")
    s.add_argument("--summary"); s.add_argument("--next"); s.add_argument("--note")
    s.add_argument("--confidence", choices=schema.CONFIDENCE); s.add_argument("--error")
    s.add_argument("--task", action="append", metavar="NAME=STATE[:SIZE]",
                   help="例: --task テスト=doing:M（STATE を - にすると削除）")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("ask", help="人間/親への質問")
    s.add_argument("--kind", required=True, choices=schema.ATTENTION_KINDS)
    s.add_argument("--q", required=True); s.add_argument("--opt", action="append")
    s.add_argument("--default"); s.add_argument("--non-blocking", action="store_true",
                                                help="既定値で作業を続けながら回答を待つ")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("ready", help="レビュー準備の自己申告")
    s.add_argument("--self-review", action="store_true"); s.add_argument("--tests", action="store_true")
    s.add_argument("--description", action="store_true"); s.add_argument("--summary")
    s.set_defaults(func=cmd_ready)

    s = sub.add_parser("pr", help="PR / CI 情報の記録")
    s.add_argument("--number", type=int); s.add_argument("--url")
    s.add_argument("--ci", choices=("pending", "pass", "fail", "none"))
    s.add_argument("--mergeable", type=lambda v: v.lower() in ("1", "true", "yes"))
    s.add_argument("--threads", type=int); s.add_argument("--review")
    s.add_argument("--state", choices=schema.STATES)
    s.set_defaults(func=cmd_pr)

    s = sub.add_parser("done", help="完了"); s.add_argument("--summary"); s.set_defaults(func=cmd_done)
    s = sub.add_parser("fail", help="失敗"); s.add_argument("--error", required=True)
    s.add_argument("--summary"); s.set_defaults(func=cmd_fail)

    s = sub.add_parser("heartbeat", help="生存通知と usage 記録（hook 用）")
    s.add_argument("--transcript"); s.add_argument("--cost", type=float)
    s.add_argument("--context-pct", type=int); s.set_defaults(func=cmd_heartbeat)

    for name, fn, hlp in (("answer", cmd_answer, "質問へ回答（親）"), ("command", cmd_command, "子へ指示（親）")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("target", help="宛先セッション ID")
        s.add_argument("--writer", default="parent", help="書き手名（既定: parent）")
        if name == "answer":
            s.add_argument("--qid", type=int, required=True); s.add_argument("--value", required=True)
        else:
            s.add_argument("--cmd", required=True); s.add_argument("--arg", action="append")
        s.set_defaults(func=fn)

    s = sub.add_parser("attention", help="要対応のセッションだけを表示（親 LLM 向け）")
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_attention)
    s = sub.add_parser("status", help="全セッションの一覧")
    s.add_argument("--json", action="store_true"); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("log", help="時系列でイベントを表示")
    s.add_argument("target", nargs="?", help="セッション ID で絞り込み")
    s.add_argument("--heartbeat", action="store_true", help="heartbeat も表示")
    s.add_argument("--tail", type=int); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_log)
    s = sub.add_parser("export", help="静的 HTML を書き出し")
    s.add_argument("--out", default="dashboard.html"); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("serve", help="リアルタイムダッシュボードを起動")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    s.add_argument("--watch-files", action="store_true",
                   help="（補助）push を使わずストアに直接書かれたイベントも 1 秒間隔で検知する")
    s.add_argument("--pull-every", type=float, default=0,
                   help="（補助）Git ストアを N 秒ごとに pull する。0 で無効（既定）")
    s.set_defaults(func=cmd_serve)
    s = sub.add_parser("hook", help="Claude Code の hook から呼ぶ（stdin に hook の JSON）")
    s.add_argument("name", choices=("session-start", "stop", "todo"))
    s.set_defaults(func=cmd_hook)
    s = sub.add_parser("flush", help="outbox に溜まった未送信イベントを再送")
    s.set_defaults(func=cmd_flush)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except schema.SchemaError as e:
        sys.exit(f"session-hub: {e}")


if __name__ == "__main__":
    main()
