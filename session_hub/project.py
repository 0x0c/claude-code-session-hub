"""Name the project a session works in, so the dashboard can group sessions by it.

The name is, in this order: the path of the `origin` remote ("owner/name"), the folder that holds
the Git repository (the main checkout, for a worktree), or the project folder itself.
"""

from __future__ import annotations

import os
import subprocess
import urllib.parse
from pathlib import Path

from . import local_state

GIT_TIMEOUT = 2


def _git(base: Path, *args: str) -> str | None:
    try:
        res = subprocess.run(["git", "-C", str(base), *args], capture_output=True, text=True,
                             timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return (res.stdout.strip() or None) if res.returncode == 0 else None


def _strip_git(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def name_from_remote(url: str) -> str | None:
    """Return "owner/name" for a remote URL, without the host and any credentials."""
    if "://" in url:
        try:
            parts = urllib.parse.urlsplit(url)
        except ValueError:
            return None
        path, local = parts.path, parts.scheme == "file"
    elif ":" in url.split("/", 1)[0]:  # scp-like form: [user@]host:owner/name.git
        path, local = url.split(":", 1)[1], False
    else:
        path, local = url, True
    path = _strip_git(path.strip("/"))
    if local:  # A path on this machine says nothing beyond its last folder
        path = path.rsplit("/", 1)[-1]
    return path if path not in ("", ".", "..") else None


def detect(cwd: str | None = None) -> str | None:
    """Return the project name for a folder (default: the session's project folder)."""
    try:
        base = Path(cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    except (OSError, RuntimeError):
        return None
    remote = _git(base, "config", "--get", "remote.origin.url")
    name = name_from_remote(remote) if remote else None
    if name:
        return name
    common = _git(base, "rev-parse", "--git-common-dir")
    if common:
        git_dir = (base / common).resolve()
        return (git_dir.parent.name if git_dir.name == ".git" else _strip_git(git_dir.name)) or None
    return base.name or None


def for_session(sid: str) -> str | None:
    """Return the project already known for this session, or detect it."""
    return local_state.load(sid).get("repo") or detect()


def remember(sid: str) -> None:
    """Keep the project in the local state, so later reports agree wherever they run."""
    st = local_state.load(sid)
    if st.get("repo"):
        return
    name = detect()
    if name:
        st["repo"] = name
        local_state.save(sid, st)
