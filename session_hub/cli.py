"""The session-hub command.

Child session:   session-hub start / report / ask / ready / pr / done / fail / learn
                 Pushes to the hub server when HUB_URL is set; otherwise writes to the local store.
Parent session:  session-hub attention / log / status / answer / command / knowledge / collection
Human:           session-hub serve (real-time dashboard) / session-hub export (static HTML) /
                 session-hub delete (remove a session's messages)
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
        sys.exit("session-hub: cannot tell the session ID. Pass --session or set HUB_SESSION_ID")
    return sid


def _record(args, fields: dict, writer: str | None = None, session: str | None = None) -> dict | None:
    """Send to the server when a push target (HUB_URL) is set; otherwise write to the local store."""
    sid = session or _session(args)
    try:
        res, mode = deliver(sid, fields, writer=writer, store_root=args.store)
    except ValueError as e:
        sys.exit(f"session-hub: {e}")
    if mode == "outbox":
        print("session-hub: the hub is unreachable; saved the event to the outbox (it is resent on the next send)", file=sys.stderr)
        return None
    if mode == "store" and client.hub_url() and not args.quiet:
        print("session-hub: the hub server is unreachable; wrote the event to the shared store (it appears when the server starts)", file=sys.stderr)
    if mode == "store":
        store = EventStore(args.store)
        if not args.no_sync and store.is_git() and not store.sync(f"hub: {sid} {res['event']['type']}"):
            print("session-hub: warning: git push failed (the event is saved locally)", file=sys.stderr)
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
        sys.exit("session-hub report: give at least one field to update")
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
    print("\n".join(lines) if lines else "(no matches)")


def cmd_collection(a):
    snap = _snap(a)
    col = snap.get("collections", {}).get(a.name)
    if not col:
        sys.exit(f"session-hub: no collection named {a.name!r} (available: {', '.join(snap.get('collections', {}))})")
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
    print("\n".join(lines) if lines else "(nothing needs action)")


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
    line(bool(sid), f"Session ID: {sid or 'unknown'}", "" if sid else "set HUB_SESSION_ID, or run inside Claude Code")
    url, store = client.hub_url(), a.store or os.environ.get("HUB_STORE")
    if url:
        line(client.is_loopback(url) or None, f"HUB_URL: {url}" + (" (local only)" if client.is_loopback(url) else " (remote host)"))
        up = client.healthy(url)
        hint = "start it with session-hub serve (with HUB_AUTOSTART=1, the next session start launches it)"
        line(up or (None if store else False), "Hub server: " + ("responding" if up else "not responding"),
             "" if up else hint + ("; until then, messages go straight to the shared store" if store else ""))
        if up:
            try:
                client.get_snapshot(url, os.environ.get("HUB_TOKEN"))
                line(True, "Authentication: OK")
            except client.PushError as e:
                line(False, f"Authentication: {e}", "use the same HUB_TOKEN as the server")
    else:
        line(None, "HUB_URL: not set (messages go straight to the shared store; the dashboard needs serve --watch-files to see them)")
    if store:
        p = Path(store).expanduser()
        writable = os.access(p if p.exists() else p.parent, os.W_OK)
        line(writable, f"HUB_STORE: {p}" + ("" if p.exists() else " (not created yet; the first write creates it)"),
             "" if writable else "point it at a writable directory")
    else:
        line(bool(url) or False, "HUB_STORE: not set", "for local use, set the same path in every session")
    line(None if not os.environ.get("HUB_AUTOSTART") else True, f"HUB_AUTOSTART: {os.environ.get('HUB_AUTOSTART', 'not set')}")
    path = shutil.which("session-hub")
    line(bool(path) or None, f"session-hub command: {path or 'not on PATH'}",
         "" if path else "the plugin's SessionStart hook creates it in ~/.local/bin; add ~/.local/bin to PATH")
    outbox = Path(os.environ.get("HUB_OUTBOX", Path.home() / ".cache" / "hub" / "outbox.jsonl"))
    n = sum(1 for _ in open(outbox, encoding="utf-8")) if outbox.exists() else 0
    line(n == 0 or None, f"Unsent events in the outbox: {n}", "" if n == 0 else "resend them with session-hub flush")
    sys.exit(0 if ok else 1)


def cmd_delete(a):
    """Physically delete every message of one session, through the hub when it runs (SH-0001)."""
    url = None if a.store else client.hub_url()
    deleted, via_store = None, True
    if url:
        try:
            res = client.delete_session(url, a.target, os.environ.get("HUB_TOKEN"))
            deleted, via_store = (res or {}).get("deleted", 0), False
        except ValueError as e:
            sys.exit(f"session-hub: {e}")
        except client.PushError as e:
            if not (a.store or os.environ.get("HUB_STORE")):
                sys.exit(f"session-hub: {e}")
            print("session-hub: the hub server is unreachable; deleting from the shared store", file=sys.stderr)
    if via_store:
        store = EventStore(a.store)
        deleted = store.delete_session(a.target)
        if deleted and not a.no_sync and store.is_git() and not store.sync(f"hub: delete {a.target}"):
            print("session-hub: warning: git push failed (the files are deleted locally)", file=sys.stderr)
    if not deleted:
        sys.exit(f"session-hub: no such session: {a.target}")
    print(f"deleted {a.target} ({deleted} events)")


def cmd_hook(a):
    from . import hooks
    hooks.run(a.name)


def cmd_flush(a):
    url = client.hub_url()
    if not url:
        sys.exit("session-hub: HUB_URL is not set")
    print(f"sent {client.flush(url, os.environ.get('HUB_TOKEN'))}")


# ---- Parser ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="session-hub", description="Share the status of Claude Code sessions through a local hub")
    p.add_argument("--store", help="event store directory (default: $HUB_STORE or .hub)")
    p.add_argument("--session", help="this session's ID (default: from the environment)")
    p.add_argument("--no-sync", action="store_true", help="do not push to Git")
    p.add_argument("-q", "--quiet", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="record the start of a session")
    s.add_argument("--title"); s.add_argument("--task-ref"); s.add_argument("--parent")
    s.add_argument("--repo"); s.add_argument("--branch"); s.add_argument("--summary")
    s.add_argument("--state", default="planning", choices=schema.STATES)
    s.add_argument("--task", action="append", metavar="NAME=STATE[:SIZE]")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("report", help="update the state and progress")
    s.add_argument("--state", choices=schema.STATES); s.add_argument("--phase")
    s.add_argument("--summary"); s.add_argument("--next"); s.add_argument("--note")
    s.add_argument("--confidence", choices=schema.CONFIDENCE); s.add_argument("--error")
    s.add_argument("--task", action="append", metavar="NAME=STATE[:SIZE]",
                   help="for example --task Tests=doing:M (a STATE of - removes the task)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("ask", help="ask a person or the parent a question")
    s.add_argument("--kind", required=True, choices=schema.ATTENTION_KINDS)
    s.add_argument("--q", required=True); s.add_argument("--opt", action="append")
    s.add_argument("--default"); s.add_argument("--non-blocking", action="store_true",
                                                help="keep working with the default while waiting for the answer")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("ready", help="declare the self-checks for review as done")
    s.add_argument("--self-review", action="store_true"); s.add_argument("--tests", action="store_true")
    s.add_argument("--description", action="store_true"); s.add_argument("--summary")
    s.set_defaults(func=cmd_ready)

    s = sub.add_parser("pr", help="record pull request and CI status")
    s.add_argument("--number", type=int); s.add_argument("--url")
    s.add_argument("--ci", choices=("pending", "pass", "fail", "none"))
    s.add_argument("--mergeable", type=lambda v: v.lower() in ("1", "true", "yes"))
    s.add_argument("--threads", type=int); s.add_argument("--review")
    s.add_argument("--state", choices=schema.STATES)
    s.set_defaults(func=cmd_pr)

    s = sub.add_parser("done", help="mark the work as done"); s.add_argument("--summary"); s.set_defaults(func=cmd_done)
    s = sub.add_parser("fail", help="mark the work as failed"); s.add_argument("--error", required=True)
    s.add_argument("--summary"); s.set_defaults(func=cmd_fail)

    s = sub.add_parser("learn", help="record a finding or caveat (it gathers in the knowledge base)")
    s.add_argument("--kind", default="insight", choices=schema.FINDING_KINDS,
                   help="caveat, insight, decision, howto (a procedure), or issue (an open problem)")
    s.add_argument("--title", required=True, help="the point in one line (up to 80 characters); the same title merges into one entry")
    s.add_argument("--body", help="details, evidence, and what to do (up to 600 characters)")
    s.add_argument("--tag", action="append", help="for example --tag ci --tag redis")
    s.add_argument("--scope", help="where it applies (a path, module, or service name)")
    s.add_argument("--key", help="an explicit key for merging entries (default: the title)")
    s.add_argument("--obsolete", action="store_true", help="mark the finding with this title as no longer true")
    s.set_defaults(func=cmd_learn)

    s = sub.add_parser("knowledge", help="print findings as short lines (for handing over to an LLM)")
    s.add_argument("--collection", default="knowledge")
    s.add_argument("--kind", action="append", choices=schema.FINDING_KINDS)
    s.add_argument("--tag", action="append"); s.add_argument("--scope")
    s.add_argument("--limit", type=int, default=30); s.add_argument("--body", action="store_true")
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_knowledge)

    s = sub.add_parser("collection", help="print a collection as Markdown or JSON")
    s.add_argument("name"); s.add_argument("--format", choices=("markdown", "json"), default="markdown")
    s.add_argument("--lang", choices=("en", "ja"), default=collections.DEFAULT_LANG)
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_collection)

    s = sub.add_parser("heartbeat", help="record a heartbeat and token usage (for hooks)")
    s.add_argument("--transcript"); s.add_argument("--cost", type=float)
    s.add_argument("--context-pct", type=int); s.set_defaults(func=cmd_heartbeat)

    for name, fn, hlp in (("answer", cmd_answer, "answer a question (parent)"), ("command", cmd_command, "send a command to a child (parent)")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("target", help="target session ID")
        s.add_argument("--writer", default="parent", help="writer name (default: parent)")
        if name == "answer":
            s.add_argument("--qid", type=int, required=True); s.add_argument("--value", required=True)
        else:
            s.add_argument("--cmd", required=True); s.add_argument("--arg", action="append")
        s.set_defaults(func=fn)

    s = sub.add_parser("attention", help="print only the sessions that need action (for the parent)")
    s.add_argument("--pull", action="store_true"); s.set_defaults(func=cmd_attention)
    s = sub.add_parser("status", help="list every session")
    s.add_argument("--json", action="store_true"); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("log", help="print events in time order")
    s.add_argument("target", nargs="?", help="filter by session ID")
    s.add_argument("--heartbeat", action="store_true", help="include heartbeats")
    s.add_argument("--tail", type=int); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_log)
    s = sub.add_parser("export", help="write a static HTML snapshot")
    s.add_argument("--out", default="dashboard.html"); s.add_argument("--pull", action="store_true")
    s.set_defaults(func=cmd_export)
    s = sub.add_parser("delete", help="delete every stored message of one session (cannot be undone)")
    s.add_argument("target", help="session ID to delete")
    s.set_defaults(func=cmd_delete)
    s = sub.add_parser("serve", help="start the real-time dashboard")
    s.add_argument("--host", default="127.0.0.1"); s.add_argument("--port", type=int, default=8765)
    s.add_argument("--watch-files", action="store_true",
                   help="(fallback) also detect events written to the store directly, every second")
    s.add_argument("--pull-every", type=float, default=0,
                   help="(fallback) pull a Git store every N seconds; 0 disables it (default)")
    s.set_defaults(func=cmd_serve)
    s = sub.add_parser("doctor", help="check the setup (URL, store, server, and command)")
    s.set_defaults(func=cmd_doctor)
    s = sub.add_parser("hook", help="called by Claude Code hooks (the hook JSON on stdin)")
    s.add_argument("name", choices=("session-start", "stop", "todo"))
    s.set_defaults(func=cmd_hook)
    s = sub.add_parser("flush", help="resend the events waiting in the outbox")
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
