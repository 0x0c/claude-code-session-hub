"""Read the pull request that Claude Code linked to the session from the transcript (JSONL)."""

from __future__ import annotations

import json
from pathlib import Path


def from_transcript(path: str | Path | None) -> dict | None:
    """Return the newest link as {"number", "url"}, or None when the session has no pull request."""
    if not path:
        return None
    link = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                # Check the text first: parsing every line of a long transcript is slow
                if '"pr-link"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "pr-link":
                    continue
                if rec.get("prNumber") and rec.get("prUrl"):
                    link = {"number": rec["prNumber"], "url": rec["prUrl"]}
    except OSError:
        return None
    return link
