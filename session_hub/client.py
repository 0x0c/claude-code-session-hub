"""push 型の送信クライアント。

HUB_URL が設定されていれば、イベントをハブサーバーへ POST する。
送れなかったイベントは outbox（ローカルの JSONL）に溜め、次回の送信時に先に再送する。
サーバー側で seq・時刻を採番するので、送信が遅れても順序はサーバー到着順で一貫する。
"""

from __future__ import annotations

import json
import os
import urllib.error
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
            # 内容の誤り・認証エラーは再送しても直らないので outbox に入れない
            raise ValueError(f"hub server rejected ({e.code}): {body}") from e
        raise PushError(f"hub server error ({e.code}): {body}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise PushError(f"hub server unreachable: {e}") from e


def get_snapshot(url: str, token: str | None = None) -> dict:
    req = urllib.request.Request(url + "/api/snapshot")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT * 2) as res:
            return json.loads(res.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PushError(f"hub server unreachable: {e}") from e


def _spool(payload: dict) -> None:
    path = _outbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def flush(url: str, token: str | None = None) -> int:
    """outbox に溜まったイベントを古い順に送る。送れた件数を返す。"""
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
            pass  # 受け付けられない内容は捨てる
        sent += 1
    path.unlink()
    return sent


def push(url: str, payload: dict, token: str | None = None) -> dict | None:
    """送信する。サーバーに届かなければ outbox に入れて None を返す。"""
    try:
        flush(url, token)
        return post(url, payload, token)
    except PushError:
        _spool(payload)
        return None
