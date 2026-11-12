"""Push-based sending client.

When HUB_URL is set, the client POSTs each event to the hub server.
An event that fails to send goes to the outbox (a local JSONL file); the next send retries it first.
The server assigns seq and the timestamp, so order follows server arrival even when a send is late.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 5


class PushError(RuntimeError):
    pass


def hub_url() -> str | None:
    url = os.environ.get("HUB_URL")
    return url.rstrip("/") if url else None


def _outbox_path() -> Path:
    return Path(os.environ.get("HUB_OUTBOX", Path.home() / ".cache" / "hub" / "outbox.jsonl"))


def post(url: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url + "/api/events", data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if 400 <= e.code < 500:
            # A bad payload or an auth error does not heal on retry, so skip the outbox
            raise ValueError(f"hub server rejected ({e.code}): {body}") from e
        raise PushError(f"hub server error ({e.code}): {body}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise PushError(f"hub server unreachable: {e}") from e


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def is_loopback(url: str) -> bool:
    return (urllib.parse.urlsplit(url).hostname or "") in LOOPBACK


def healthy(url: str, timeout: float = 0.7) -> bool:
    try:
        with urllib.request.urlopen(url + "/healthz", timeout=timeout) as res:
            return res.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def get_snapshot(url: str, token: str | None = None) -> dict:
    req = urllib.request.Request(url + "/api/snapshot")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT * 2) as res:
            return json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PushError(f"hub server unreachable: {e}") from e


def spool(payload: dict) -> None:
    path = _outbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def flush(url: str, token: str | None = None) -> int:
    """Send the outbox events oldest first and return how many were sent."""
    path = _outbox_path()
    if not path.exists():
        return 0
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    sent = 0
    for i, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            sent += 1
            continue
        try:
            post(url, payload, token)
        except PushError:
            path.write_text("\n".join(lines[i:]) + "\n", encoding="utf-8")
            return sent
        except ValueError:
            pass  # Drop a payload the server rejects
        sent += 1
    path.unlink()
    return sent


def push(url: str, payload: dict, token: str | None = None) -> dict | None:
    """Send the event; if the server is unreachable, queue it in the outbox and return None."""
    try:
        flush(url, token)
        return post(url, payload, token)
    except PushError:
        spool(payload)
        return None
