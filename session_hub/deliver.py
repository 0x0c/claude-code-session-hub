"""メッセージ（サブセッションからの更新）の配送。CLI と hook の共通処理。

配送の優先順:
    1. HUB_URL のハブサーバーへ push（ダッシュボードに即時反映）
    2. サーバーに届かず、HUB_STORE があれば、共有ストアへ直接書く
       （ローカル運用。サーバーが起動したとき、または次の push / 30 秒ごとの再判定で画面に出る）
    3. どちらもなければ outbox に溜め、次の送信時に再送する
"""

from __future__ import annotations

import os

from . import client, core, local_state
from .store import EventStore


def store_configured(store_root=None) -> bool:
    return bool(store_root or os.environ.get("HUB_STORE"))


def deliver(session_id: str, fields: dict, writer: str | None = None, store_root=None) -> tuple[dict | None, str]:
    """戻り値: (記録結果 or None, 経路 "push" | "store" | "outbox")。

    サーバーが内容を拒否した（4xx）場合は ValueError をそのまま送出する。
    """
    payload = {"session_id": session_id, "writer": writer, "fields": fields}
    url = client.hub_url()
    res, mode = None, "outbox"
    if url:
        token = os.environ.get("HUB_TOKEN")
        try:
            client.flush(url, token)
            res, mode = client.post(url, payload, token), "push"
        except client.PushError:
            if store_configured(store_root):
                res, mode = core.record(EventStore(store_root), session_id, fields, writer=writer), "store"
            else:
                client.spool(payload)
    else:
        res, mode = core.record(EventStore(store_root), session_id, fields, writer=writer), "store"
    if writer is None:
        local_state.note(session_id, fields, res)
    return res, mode
