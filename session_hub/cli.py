"""The session-hub command.

Child session:   session-hub start / report / ask / ready / pr / done / fail / learn
                 Pushes to the hub server when HUB_URL is set; otherwise writes to the local store.
Parent session:  session-hub attention / log / status / answer / command / knowledge / collection
Human:           session-hub serve (real-time dashboard) / session-hub export (static HTML)
Hook:            session-hub hook session-start|stop|todo (hook JSON on stdin)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import client, collections, core, local_state, schema, view
from .deliver import deliver
from .store import EventStore, current_session_id
from .usage import usage_from_transcript

PROTOCOL = core.PROTOCOL


def _session(args) -> str:
    sid = args.session or current_session_id()
    if not sid:
        sys.exit("session-hub: セッション ID が分かりません。--session か HUB_SESSION_ID を指定してください")
    return sid


def _record(args, fields: dict, writer: str | None = None, session: str | None = None) -> dict | None:
    """Send to the server when a push target (HUB_URL) is set; otherwise write to the local store."""
    sid = session or _session(args)
    try:
        res, mode = deliver(sid, fields, writer=writer, store_root=args.store)
    except ValueError as e:
        sys.exit(f"session-hub: {e}")
    if mode == "outbox":
        print("session-hub: ハブに届かないため outbox に保存しました（次回送信時に再送）", file=sys.stderr)
        return None
    if mode == "store" and client.hub_url() and not args.quiet:
        print("session-hub: ハブサーバーに届かないため共有ストアに直接書きました（サーバー起動時に反映）", file=sys.stderr)
    if mode == "store":
        store = EventStore(args.store)
        if not args.no_sync and store.is_git() and not store.sync(f"hub: {sid} {res['event']['type']}"):
            print("session-hub: 警告: git push に失敗しました（イベントはローカルに保存済み）", file=sys.stderr)
    # For a transition that should wake the parent, message holds one line ready for send_message
    if res["escalate"] or not args.quiet:
        print(res["message"])
    return res


# ---- Subcommands ----------------------------------------------------------

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


def cmd_learn(a):
    finding = {"kind": a.kind, "title": a.title, "body": a.body, "tags": a.tag or [],
               "scope": a.scope, "key": a.key, "status": "obsolete" if a.obsolete else "active"}
    _record(a, {"type": "finding", "finding": {k: v for k, v in finding.items() if v not in (None, "")}})


def cmd_knowledge(a):
    lines = view.knowledge_lines(_snap(a), name=a.collection, kinds=a.kind, tags=a.tag, scope=a.scope,
                                 limit=a.limit, with_body=a.body)
    print("\n".join(lines) if lines else "(該当なし)")


def cmd_collection(a):
    snap = _snap(a)
    col = snap.get("collections", {}).get(a.name)
    if not col:
        sys.exit(f"session-hub: コレクション {a.name!r} はありません（{', '.join(snap.get('collections', {}))}）")
    if a.format == "json":
        print(json.dumps(col, ensure_ascii=False, indent=2))
    else:
        titles = {s["session_id"]: s.get("title") or s["session_id"] for s in snap["sessions"]}
        print(collections.render_markdown(col, titles, a.lang), end="")


def cmd_heartbeat(a):
    usage = {}
    if a.transcript:
        usage = usage_from_transcript(a.transcript)
    elif not sys.stdin.isatty():
        # A Claude Code hook passes {"transcript_path": ...} on stdin
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
    return view.snapshot(store.read_all(), defs=collections.load_definitions(store.root))


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


def cmd_doctor(a):
    """Check the configuration; exit with status 1 on any problem."""
    import shutil
    ok = True

    def line(good, msg, hint=""):
        nonlocal ok
        ok = ok and good is not False
        mark = {True: "OK  ", False: "NG  ", None: "--  "}[good]
        print(mark + msg + (f"\n      → {hint}" if hint else ""))

    sid = a.session or current_session_id()
    line(bool(sid), f"セッション ID: {sid or '不明'}", "" if sid else "HUB_SESSION_ID を設定するか Claude Code 内で実行する")
    url, store = client.hub_url(), a.store or os.environ.get("HUB_STORE")
    if url:
        line(client.is_loopback(url) or None, f"HUB_URL: {url}" + ("（ローカルのみ）" if client.is_loopback(url) else "（外部ホスト）"))
        up = client.healthy(url)
        hint = "session-hub serve を起動する（HUB_AUTOSTART=1 なら次のセッション開始時に自動起動）"
        line(up or (None if store else False), "ハブサーバー: " + ("応答あり" if up else "応答なし"),
             "" if up else hint + ("。それまでは共有ストアに直接書く" if store else ""))
        if up:
            try:
                client.get_snapshot(url, os.environ.get("HUB_TOKEN"))
                line(True, "認証: OK")
            except client.PushError as e:
                line(False, f"認証: {e}", "HUB_TOKEN をサーバーと揃える")
    else:
        line(None, "HUB_URL: 未設定（push せず共有ストアに直接書く。画面への反映は serve --watch-files が必要）")
    if store:
        p = Path(store).expanduser()
        writable = os.access(p if p.exists() else p.parent, os.W_OK)
        line(writable, f"HUB_STORE: {p}" + ("" if p.exists() else "（未作成。最初の書き込みで作られる）"),
             "" if writable else "書き込めるディレクトリを指定する")
    else:
        line(bool(url) or False, "HUB_STORE: 未設定", "ローカル運用では全セッションで同じパスを設定する")
    line(None if not os.environ.get("HUB_AUTOSTART") else True, f"HUB_AUTOSTART: {os.environ.get('HUB_AUTOSTART', '未設定')}")
    path = shutil.which("session-hub")
    line(bool(path) or None, f"session-hub コマンド: {path or 'PATH にない'}",
         "" if path else "プラグインの SessionStart hook が ~/.local/bin に作る。PATH に ~/.local/bin を追加する")
    outbox = Path(os.environ.get("HUB_OUTBOX", Path.home() / ".cache" / "hub" / "outbox.jsonl"))
    n = sum(1 for _ in open(outbox, encoding="utf-8")) if outbox.exists() else 0
    line(n == 0 or None, f"未送信の outbox: {n} 件", "" if n == 0 else "session-hub flush で再送する")
    sys.exit(0 if ok else 1)


def cmd_hook(a):
    from . import hooks
    hooks.run(a.name)


def cmd_flush(a):
    url = client.hub_url()
    if not url:
        sys.exit("hub: HUB_URL が設定されていません")
    print(f"sent {client.flush(url, os.environ.get('HUB_TOKEN'))}")


# ---- Parser ---------------------------------------------------------------

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

    s = sub.add_parser("learn", help="作業で判明した知見・注意点を記録（ナレッジに集約される）")
    s.add_argument("--kind", default="insight", choices=schema.FINDING_KINDS,
                   help="caveat=注意点 insight=知見 decision=決定事項 howto=手順 issue=未解決の問題")
    s.add_argument("--title", required=True, help="1 行の要点（80 文字まで）。同じ要点は 1 件にまとまる")
    s.add_argument("--body", help="詳細・根拠・対処（600 文字まで）")
    s.add_argument("--tag", action="append", help="例: --tag ci --tag redis")
    s.add_argument("--scope", help="関係する場所（パス、モジュール、サービス名など）")
    s.add_argument("--key", help="まとめる単位を明示したいときのキー（既定は title）")
    s.add_argument("--obsolete", action="store_true", help="同じ要点を「もう当てはまらない」にする")
    s.set_defaults(func=cmd_learn)

    s = sub.add_parser("knowledge", help="集まった知見を短い行で表示（LLM への引き継ぎ用）")
    s.add_argument("--collection", default="knowledge")
    s.add_argument("--kind", action="append", choices=schema.FINDING_KINDS)
    s.add_argument("--tag", action="append"); s.add_argument("--scope")
    s.add_argument("--limit", type=int, default=30); s.add_argument("--body", action="store_true")
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_knowledge)

    s = sub.add_parser("collection", help="コレクションを Markdown / JSON で出力")
    s.add_argument("name"); s.add_argument("--format", choices=("markdown", "json"), default="markdown")
    s.add_argument("--lang", choices=("ja", "en"), default=collections.DEFAULT_LANG)
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_collection)

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
    s = sub.add_parser("doctor", help="設定（URL・ストア・サーバー・コマンド）を確認")
    s.set_defaults(func=cmd_doctor)
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
    except (schema.SchemaError, collections.CollectionError) as e:
        sys.exit(f"session-hub: {e}")


if __name__ == "__main__":
    main()
