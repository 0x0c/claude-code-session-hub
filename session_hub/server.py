"""ハブサーバー（push 型・標準ライブラリのみ）。

流れ:
    子セッション ──POST /api/events──► サーバー ──記録──► ストア
                                          └──即時配信（SSE）──► ブラウザ

- 子セッションは `session-hub report` などを実行すると、HUB_URL のこのサーバーへ イベントを POST する。
- サーバーは受け取ったイベントを検証してストアに追記し、その場で接続中のブラウザへ
  Server-Sent Events で差分を送る。ブラウザ側もサーバー側もポーリングしない。
- 経過時間だけで変わる判定（停滞検知、「◯分前」）のため、30 秒ごとに状態を送り直す。
- 補助: `--watch-files`（ストアへの直接書き込みを検知）、`--pull-every`（Git ストアの pull）。

エンドポイント:
    GET  /              ダッシュボード（HTML）
    GET  /api/snapshot  全データ（JSON）
    GET  /api/stream    SSE。最初に snapshot、以後 update
    POST /api/events    イベント受信 {"session_id", "writer"?, "fields": {...}}
"""

from __future__ import annotations

import hmac
import json
import urllib.parse
from http.cookies import SimpleCookie
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from . import core, schema, view
from .store import EventStore

MAX_BODY = 64 * 1024


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class Hub:
    """イベントの受信・記録と、SSE クライアントへの配信を受け持つ。"""

    def __init__(self, store: EventStore, watch_files: bool = False, pull_every: float = 0,
                 refresh_every: float = 30.0, ping_every: float = 15.0):
        self.store = store
        self.watch_files = watch_files
        self.pull_every = pull_every
        self.refresh_every = refresh_every
        self.ping_every = ping_every
        self.lock = threading.Lock()        # snapshot とクライアント集合
        self.write_lock = threading.Lock()  # 記録 → 配信 を 1 件ずつ直列化
        self.clients: set[queue.Queue] = set()
        self.snap = view.snapshot(store.read_all())
        self._event_index = self._index(self.snap)
        self._sig = store.signature()
        self._stop = threading.Event()

    @staticmethod
    def _index(snap: dict) -> dict[str, str]:
        return {e["id"]: _dumps(e) for e in snap["events"]}

    # ---- 受信（push） ----
    def ingest(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("fields"), dict):
            raise schema.SchemaError("body は {session_id, writer?, fields:{...}} の形式です")
        sid = payload.get("session_id")
        if not isinstance(sid, str):
            raise schema.SchemaError("session_id は必須です")
        writer = payload.get("writer") or None
        fields = {k: v for k, v in payload["fields"].items() if k not in ("session_id", "seq", "ts")}
        with self.write_lock:
            res = core.record(self.store, sid, fields, writer=writer)  # seq と時刻はサーバーが採番
            self.publish()
        return res

    # ---- クライアント管理 ----
    def subscribe(self) -> tuple[queue.Queue, dict]:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self.lock:
            self.clients.add(q)
            return q, self.snap

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients.discard(q)

    def _send(self, q: queue.Queue, msg: str) -> None:
        try:
            q.put_nowait(msg)
        except queue.Full:
            # 読みが追いつかないクライアントは切り離す。ブラウザは自動再接続し、
            # 新しい snapshot から取り直すので取りこぼしは起きない。
            self.clients.discard(q)
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
            q.put_nowait(None)

    def _broadcast(self, event: str, data: dict) -> None:
        msg = f"event: {event}\ndata: {_dumps(data)}\n\n"
        for q in list(self.clients):
            self._send(q, msg)

    # ---- 配信 ----
    def publish(self, force: bool = False) -> bool:
        """ストアの内容から snapshot を作り直し、変化分を全クライアントへ送る。"""
        snap = view.snapshot(self.store.read_all())
        index = self._index(snap)
        with self.lock:
            changed = [e for e in snap["events"] if self._event_index.get(e["id"]) != index[e["id"]]]
            removed = [i for i in self._event_index if i not in index]
            self.snap, self._event_index, self._sig = snap, index, self.store.signature()
            if changed or removed or force:
                self._broadcast("update", {"generated_at": snap["generated_at"],
                                           "sessions": snap["sessions"], "total": snap["total"],
                                           "events": changed, "removed": removed})
        return bool(changed or removed)

    def run(self) -> None:
        """定期処理: keepalive、時間経過による再判定、（補助）ファイル監視・Git pull。"""
        last_refresh = last_ping = last_pull = time.monotonic()
        tick = 1.0 if (self.watch_files or self.pull_every) else min(self.ping_every, self.refresh_every)
        while not self._stop.wait(tick):
            t = time.monotonic()
            try:
                if self.pull_every and self.store.is_git() and t - last_pull >= self.pull_every:
                    self.store.pull()
                    last_pull = t
                if (self.watch_files or self.pull_every) and self.store.signature() != self._sig:
                    with self.write_lock:
                        self.publish()
                if t - last_refresh >= self.refresh_every:
                    with self.write_lock:
                        self.publish(force=True)
                    last_refresh = t
            except Exception as exc:  # 一時的な失敗で定期処理を止めない
                print(f"hub: periodic task failed: {exc}", flush=True)
            if t - last_ping >= self.ping_every:
                with self.lock:
                    for q in list(self.clients):
                        self._send(q, ": ping\n\n")
                last_ping = t

    def stop(self) -> None:
        self._stop.set()
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass


def dashboard_html() -> str:
    return resources.files("session_hub").joinpath("templates/dashboard.html").read_text(encoding="utf-8")


def make_handler(hub: Hub, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: str, ctype: str = "application/json; charset=utf-8") -> None:
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self) -> bool:
            """Authorization ヘッダー、cookie、?token= のいずれかで認証（トークン未設定なら常に可）。"""
            if not token:
                return True
            want = token.encode()
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].encode(), want):
                return True
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            if "hub_token" in cookie and hmac.compare_digest(cookie["hub_token"].value.encode(), want):
                return True
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token", [""])[0]
            return bool(q) and hmac.compare_digest(q.encode(), want)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                return self._send(200, "ok", "text/plain")
            if not self._authorized():
                return self._send(401, "unauthorized: URL に ?token=<HUB_TOKEN> を付けて開いてください",
                                  "text/plain; charset=utf-8")
            if path in ("/", "/index.html") and "token=" in self.path:
                # 一度だけ URL でトークンを受け取り、以後は cookie で認証（URL からトークンを消す）
                self.send_response(303)
                self.send_header("Set-Cookie", f"hub_token={token}; Path=/; HttpOnly; SameSite=Strict")
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path in ("/", "/index.html"):
                self._send(200, dashboard_html(), "text/html; charset=utf-8")
            elif path == "/api/snapshot":
                with hub.lock:
                    snap = hub.snap
                self._send(200, _dumps(snap))
            elif path == "/api/stream":
                self._stream()
            else:
                self._send(404, _dumps({"error": "not found"}))

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/events":
                return self._send(404, _dumps({"error": "not found"}))
            if not self._authorized():
                return self._send(401, _dumps({"error": "unauthorized"}))
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length <= 0 or length > MAX_BODY:
                return self._send(413 if length > MAX_BODY else 400, _dumps({"error": "bad body size"}))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                res = hub.ingest(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._send(400, _dumps({"error": "invalid json"}))
            except schema.SchemaError as e:
                return self._send(400, _dumps({"error": str(e)}))
            self._send(201, _dumps(res))

        def _stream(self):
            q, snap = hub.subscribe()
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.wfile.write(f"retry: 3000\nevent: snapshot\ndata: {_dumps(snap)}\n\n".encode())
                self.wfile.flush()
                while True:
                    msg = q.get()
                    if msg is None:
                        break
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unsubscribe(q)
                self.close_connection = True

    return Handler


def make_server(store: EventStore, host: str = "127.0.0.1", port: int = 8765, token: str | None = None,
                watch_files: bool = False, pull_every: float = 0) -> tuple[ThreadingHTTPServer, Hub]:
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit("hub: localhost 以外で待ち受けるときは HUB_TOKEN を設定してください")
    hub = Hub(store, watch_files=watch_files, pull_every=pull_every)
    httpd = ThreadingHTTPServer((host, port), make_handler(hub, token))
    httpd.daemon_threads = True
    return httpd, hub


def serve(store: EventStore, host: str = "127.0.0.1", port: int = 8765, token: str | None = None,
          watch_files: bool = False, pull_every: float = 0) -> None:
    httpd, hub = make_server(store, host, port, token, watch_files, pull_every)
    threading.Thread(target=hub.run, daemon=True).start()
    print(f"hub server: http://{host}:{httpd.server_address[1]}/  (store: {store.root}, "
          f"auth: {'on' if token else 'off'})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        httpd.server_close()
