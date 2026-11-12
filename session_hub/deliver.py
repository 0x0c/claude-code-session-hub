"""Delivery of messages (updates from sub-sessions), shared by the CLI and the hooks.

Delivery order:
    1. Push to the hub server at HUB_URL (the dashboard shows the update at once).
    2. If the server is unreachable and HUB_STORE is set, write to the shared store directly
       (local use; the update appears when the server starts, on the next push, or on the
       30-second recheck).
    3. Otherwise, queue the event in the outbox and retry it on the next send.
"""

from __future__ import annotations

import os

from . import client, core, local_state
from .store import EventStore


def store_configured(store_root=None) -> bool:
    return bool(store_root or os.environ.get("HUB_STORE"))


def deliver(session_id: str, fields: dict, writer: str | None = None, store_root=None) -> tuple[dict | None, str]:
    """Return (recorded result or None, route "push" | "store" | "outbox").

    If the server rejects the payload (4xx), the ValueError propagates unchanged.
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
