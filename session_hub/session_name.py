"""Read the session's name, as Claude Code shows it, from the transcript (JSONL)."""

from __future__ import annotations

import json
from pathlib import Path

# The record types that carry a name, and the field that holds it. A name that a person or the host
# app set ("custom-title") wins over the name Claude Code generated ("ai-title").
NAME_FIELDS = {"custom-title": "customTitle", "ai-title": "aiTitle"}


def from_transcript(path: str | Path | None) -> str | None:
    """Return the newest name in the transcript, or None when the session has no name."""
    if not path:
        return None
    names: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # Check the text first: parsing every line of a long transcript is slow
                if not any(f'"{kind}"' in line for kind in NAME_FIELDS):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") not in NAME_FIELDS:
                    continue
                name = rec.get(NAME_FIELDS[rec["type"]])
                if isinstance(name, str) and name.strip():
                    names[rec["type"]] = " ".join(name.split())
    except OSError:
        return None
    return names.get("custom-title") or names.get("ai-title")
