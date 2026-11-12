"""Handlers that Claude Code hooks call. They catch missed child-session reports at almost no token cost.

    session-start  : install the CLI shim (~/.local/bin/session-hub) and inject short instructions
                     into the context
    stop           : send a heartbeat and usage automatically at the end of each turn.
                     If a turn ends while the state is still "working", prompt for a report once
    todo           : send progress (tasks) automatically from TodoWrite, TaskCreate, and TaskUpdate

Every hook does nothing unless HUB_URL or HUB_STORE is set.
To keep an exception from stopping the Claude Code session, each hook swallows failures and exits 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

from . import client, local_state
from .deliver import deliver
from .store import current_session_id
from .usage import usage_from_transcript

ACTIVE_STATES = ("planning", "working", "changes_requested")
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def enabled() -> bool:
    return bool(os.environ.get("HUB_URL") or os.environ.get("HUB_STORE"))


def send(fields: dict, writer: str | None = None) -> dict | None:
    sid = current_session_id()
    if not sid:
        return None
    try:
        return deliver(sid, fields, writer=writer)[0]
    except ValueError:
        return None


def _read_payload() -> dict:
    try:
        data = sys.stdin.read()
        return json.loads(data) if data.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ---- session-start ---------------------------------------------------------

def install_shim() -> Path | None:
    """When loaded as a plugin, make `session-hub` callable from Bash."""
    target = PLUGIN_ROOT / "bin" / "session-hub"
    if not target.exists():
        return None
    shim = Path.home() / ".local" / "bin" / "session-hub"
    try:
        shim.parent.mkdir(parents=True, exist_ok=True)
        content = f'#!/bin/sh\nexec "{target}" "$@"\n'
        if not shim.exists() or shim.read_text() != content:
            shim.write_text(content)
            shim.chmod(0o755)
    except OSError:
        return None
    return shim


def autostart_server() -> str | None:
    """With HUB_AUTOSTART=1, start the local hub server in the background if it is not running.

    Local use alone: this runs only when HUB_URL points to 127.0.0.1 or localhost and HUB_STORE is set.
    When several sessions start at once, a server that fails to bind the port exits at once,
    which does no harm.
    """
    url = client.hub_url()
    store = os.environ.get("HUB_STORE")
    if os.environ.get("HUB_AUTOSTART") != "1" or not url or not store or not client.is_loopback(url):
        return None
    if client.healthy(url):
        return "running"
    parts = urllib.parse.urlsplit(url)
    log = Path(store).expanduser() / ".server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(PLUGIN_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    with open(log, "ab") as out:
        subprocess.Popen(
            [sys.executable, "-m", "session_hub", "serve", "--host", parts.hostname, "--port", str(parts.port or 80)],
            env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
    return "started"


def session_start(payload: dict) -> str:
    shim = install_shim()
    if not enabled():
        return ""
    try:
        autostart_server()
    except OSError as exc:
        print(f"session-hub: could not start the server automatically: {exc}", file=sys.stderr)
    sid = current_session_id()
    st = local_state.load(sid) if sid else {}
    cmd = "session-hub"
    if shim and str(shim.parent) not in os.environ.get("PATH", "").split(":"):
        cmd = str(shim)
    lines = [f"[session-hub] This session's status is pushed to a dashboard (session_id={sid})."
             f" Follow the session-hub-report skill: report with `{cmd}` whenever your state changes."]
    if not st.get("started"):
        lines.append(f"Not registered yet: first run `{cmd} start --title \"<work>\" --task \"<task>=todo\" ...`.")
    else:
        lines.append(f"Last report: state={st.get('state')}. When you resume, run `{cmd} report --state working --summary ...`.")
    return "\n".join(lines)


# ---- stop -----------------------------------------------------------------

def stop(payload: dict) -> str:
    if not enabled():
        return ""
    sid = current_session_id()
    if not sid:
        return ""
    usage = {}
    if payload.get("transcript_path"):
        usage = usage_from_transcript(payload["transcript_path"])
    send({"type": "heartbeat", "actor": "hook", "usage": usage})

    if os.environ.get("HUB_STOP_GUARD", "1") == "0" or payload.get("stop_hook_active"):
        return ""
    st = local_state.load(sid)
    if not st.get("started"):
        reason = ("This session is not registered with session-hub yet. Register the work with "
                  "`session-hub start --title ...` before ending the turn (if you are not working on "
                  "anything, use `session-hub start --state queued --title ...`).")
    elif st.get("state") in ACTIVE_STATES:
        reason = ("The dashboard still shows this session as working. Before ending the turn, report "
                  "the current state in one line: done -> `session-hub done`, a question -> "
                  "`session-hub ask`, a PR ready for review -> `session-hub ready ...`, waiting for CI "
                  "or something external -> `session-hub report --state waiting_ci|blocked --summary ...`, "
                  "failed -> `session-hub fail --error ...`.")
    else:
        return ""
    return json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)


# ---- todo -----------------------------------------------------------------

TODO_MAP = {"pending": "todo", "in_progress": "doing", "completed": "done", "deleted": "-", "cancelled": "skip"}


def _clean(name: str) -> str:
    return " ".join(str(name).replace("=", "＝").split())[:40]


def todo(payload: dict) -> str:
    if not enabled():
        return ""
    sid = current_session_id()
    tool = payload.get("tool_name")
    inp = payload.get("tool_input") or {}
    if not sid or not isinstance(inp, dict):
        return ""
    fields: dict = {"type": "report", "actor": "hook"}

    if tool == "TodoWrite" and isinstance(inp.get("todos"), list):
        tasks, summary = [], None
        for t in inp["todos"]:
            s = TODO_MAP.get(t.get("status"), "todo")
            if s == "-":
                continue
            tasks.append({"t": _clean(t.get("content", "")), "s": s, "size": "M"})
            if s == "doing" and t.get("activeForm"):
                summary = t["activeForm"]
        fields["tasks"] = tasks
        if summary:
            fields["summary"] = summary
    elif tool == "TaskCreate" and inp.get("subject"):
        name = _clean(inp["subject"])
        task_id = _find_task_id(payload.get("tool_response"))
        if task_id:
            local_state.map_task(sid, task_id, name)
        fields["task_updates"] = [f"{name}=todo"]
    elif tool == "TaskUpdate" and inp.get("taskId") is not None:
        name = local_state.task_name(sid, str(inp["taskId"]))
        status = TODO_MAP.get(inp.get("status"))
        if inp.get("subject"):
            new = _clean(inp["subject"])
            if name and new != name:
                fields.setdefault("task_updates", []).append(f"{name}=-")
            local_state.map_task(sid, str(inp["taskId"]), new)
            name = new
        if not name or not status:
            return ""
        fields.setdefault("task_updates", []).append(f"{name}={status}")
        if status == "doing" and inp.get("activeForm"):
            fields["summary"] = inp["activeForm"]
    else:
        return ""
    # Once a task starts, move a planning or queued state to working (never override asking and similar states)
    doing = any(t["s"] == "doing" for t in fields.get("tasks", [])) or any(
        u.endswith("=doing") for u in fields.get("task_updates", []))
    if doing and local_state.load(sid).get("state") in (None, "queued", "planning"):
        fields["state"] = "working"
    send(fields)
    return ""


def _find_task_id(resp) -> str | None:
    if isinstance(resp, dict):
        for key in ("taskId", "id", "task_id"):
            if resp.get(key) is not None:
                return str(resp[key])
        for v in resp.values():
            found = _find_task_id(v)
            if found:
                return found
    elif isinstance(resp, list):
        for v in resp:
            found = _find_task_id(v)
            if found:
                return found
    elif isinstance(resp, str):
        m = re.search(r"#(\d+)", resp) or re.search(r"\bid[\"':\s]+(\w+)", resp)
        return m.group(1) if m else None
    return None


HANDLERS = {"session-start": session_start, "stop": stop, "todo": todo}


def run(name: str) -> None:
    try:
        out = HANDLERS[name](_read_payload())
    except Exception as exc:  # A hook failure must not stop the session
        print(f"session-hub hook {name}: {exc}", file=sys.stderr)
        return
    if out:
        print(out)
