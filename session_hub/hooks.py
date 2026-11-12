"""Claude Code の hook から呼ばれる処理。子セッションの報告漏れを、トークンをほぼ使わずに防ぐ。

    session-start  : CLI のシム（~/.local/bin/session-hub）を用意し、短い手順をコンテキストへ注入
    stop           : ターン終了ごとに heartbeat と usage を自動送信。
                     状態が「作業中」のままターンを終えようとしたら 1 回だけ報告を促す
    todo           : TodoWrite / TaskCreate / TaskUpdate の内容から進捗（tasks）を自動送信

どの hook も、HUB_URL か HUB_STORE が設定されていなければ何もしない。
また例外で Claude Code のセッションを止めないよう、失敗は握りつぶして終了コード 0 で返る。
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
    """プラグインとして読み込まれたとき、Bash から `session-hub` で呼べるようにする。"""
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
    """HUB_AUTOSTART=1 のとき、ローカルのハブサーバーが動いていなければ裏で起動する。

    ローカル運用専用: HUB_URL が 127.0.0.1 / localhost を指し、HUB_STORE があるときだけ動く。
    複数のセッションが同時に起動しても、ポートを取れなかった側はすぐ終了するだけで害はない。
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
        print(f"session-hub: サーバーの自動起動に失敗: {exc}", file=sys.stderr)
    sid = current_session_id()
    st = local_state.load(sid) if sid else {}
    cmd = "session-hub"
    if shim and str(shim.parent) not in os.environ.get("PATH", "").split(":"):
        cmd = str(shim)
    lines = [f"[session-hub] このセッションの状況はダッシュボードに push される（session_id={sid}）。"
             f" session-hub:report スキルの手順で、状態が変わるたびに `{cmd}` で報告すること。"]
    if not st.get("started"):
        lines.append(f"未登録: 最初に `{cmd} start --title \"<作業名>\" --task \"<タスク>=todo\" ...` を実行する。")
    else:
        lines.append(f"前回の報告: state={st.get('state')}。再開したら `{cmd} report --state working --summary ...`。")
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
        reason = ("session-hub にまだ登録されていません。`session-hub start --title ...` で作業内容を登録してから"
                  "ターンを終えてください（作業していないなら `session-hub start --state queued --title ...`）。")
    elif st.get("state") in ACTIVE_STATES:
        reason = ("ダッシュボード上は「作業中」のままです。ターンを終える前に今の状態を 1 行で報告してください: "
                  "完了→`session-hub done`、質問→`session-hub ask`、PR 準備完了→`session-hub ready ...`、"
                  "CI/外部待ち→`session-hub report --state waiting_ci|blocked --summary ...`、"
                  "失敗→`session-hub fail --error ...`。")
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
    # タスクに着手したら、計画中/待機中の表示を自動で作業中へ（質問中などは上書きしない）
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
    except Exception as exc:  # hook の失敗でセッションを止めない
        print(f"session-hub hook {name}: {exc}", file=sys.stderr)
        return
    if out:
        print(out)
