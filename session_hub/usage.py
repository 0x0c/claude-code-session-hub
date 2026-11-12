"""トランスクリプト（JSONL）からトークン使用量を合算する。hook から呼ぶ。"""

from __future__ import annotations

import json
from pathlib import Path


def usage_from_transcript(path: str | Path) -> dict:
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "turns": 0}
    seen: set[str] = set()
    p = Path(path)
    if not p.exists():
        return totals
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = rec.get("message") if isinstance(rec, dict) else None
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            # ストリーミングで同じメッセージが複数行に分かれることがあるので ID で重複排除
            mid = msg.get("id") or rec.get("uuid")
            if mid in seen:
                continue
            seen.add(mid)
            totals["input"] += usage.get("input_tokens") or 0
            totals["output"] += usage.get("output_tokens") or 0
            totals["cache_read"] += usage.get("cache_read_input_tokens") or 0
            totals["cache_write"] += usage.get("cache_creation_input_tokens") or 0
            totals["turns"] += 1
    return totals
