"""The knowledge store: one durable record per revision of a knowledge entry.

The event store keeps a short `finding` notice on the timeline; the full text of the finding lives
here, under `<store>/knowledge/`. Each file has one writer, as in the event store, so sharing the
store through Git never produces a merge conflict: `<session-id>.jsonl` for a sub-session and
`<session-id>@<writer>.jsonl` for the parent.

A line is one revision of one entry. The entry is named by a short hash of the finding's key (the
title when no key is given), so two sessions that report the same caveat append to the same entry.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

from . import collections
from .store import EventStore, _check_id

FIELDS = ("kind", "title", "body", "tags", "scope", "key", "status")
NOTICE_FIELDS = ("kind", "title", "key", "status")  # what the timeline event keeps


def entry_id(finding: dict) -> str:
    """Name an entry by a short hash of its normalized key (or title)."""
    return collections.entry_id(finding.get("key") or finding.get("title") or "")


def notice(finding: dict) -> dict:
    """Return the part of a finding that stays on the timeline."""
    return {k: finding[k] for k in NOTICE_FIELDS if k in finding}


class KnowledgeStore:
    def __init__(self, root: Path | str):
        self.dir = Path(root) / "knowledge"

    def _path(self, session_id: str, writer: str | None) -> Path:
        _check_id(session_id, "session_id")
        if writer:
            _check_id(writer, "writer")
            return self.dir / f"{session_id}@{writer}.jsonl"
        return self.dir / f"{session_id}.jsonl"

    def _append_lines(self, session_id: str, writer: str | None, records: list[dict]) -> None:
        if not records:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._path(session_id, writer), "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _record(ev: dict, finding: dict) -> dict:
        return {"entry": entry_id(finding), "event_id": ev["id"], "session_id": ev["session_id"],
                "writer": ev.get("writer"), "ts": ev["ts"],
                **{k: finding[k] for k in FIELDS if k in finding}}

    def append(self, ev: dict, finding: dict) -> dict:
        """Write one revision for the timeline event `ev`, and return the record."""
        rec = self._record(ev, finding)
        self._append_lines(ev["session_id"], ev.get("writer"), [rec])
        return rec

    def read(self) -> list[dict]:
        """Return every revision record in time order; a corrupt line is skipped."""
        out, seen = [], set()
        for path in sorted(self.dir.glob("*.jsonl")) if self.dir.exists() else []:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        key = (rec["event_id"], rec["entry"])
                        rec["title"], rec["ts"], rec["session_id"]
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
                    if key in seen:  # a duplicate line from a Git merge
                        continue
                    seen.add(key)
                    out.append(rec)
        out.sort(key=lambda r: (r["ts"], r["event_id"]))
        return out

    def import_events(self, all_events: dict[str, list[dict]]) -> int:
        """Copy finding events that the store does not hold yet; return how many were copied.

        Events written before the store existed carry the full text, so a second run copies nothing.
        """
        known = {r["event_id"] for r in self.read()}
        fresh: dict[tuple, list[dict]] = {}
        for evs in all_events.values():
            for ev in evs:
                if ev["type"] == "finding" and ev["id"] not in known and ev.get("finding"):
                    fresh.setdefault((ev["session_id"], ev.get("writer")), []).append(self._record(ev, ev["finding"]))
        for (sid, writer), recs in fresh.items():
            self._append_lines(sid, writer, recs)
        return sum(len(r) for r in fresh.values())

    @staticmethod
    def as_events(records: list[dict]) -> list[dict]:
        """Shape revision records like finding events, so that a collection can project them."""
        return [{"id": r["event_id"], "session_id": r["session_id"], "writer": r.get("writer"), "seq": 0,
                 "ts": r["ts"], "type": "finding", "finding": {k: r[k] for k in FIELDS if k in r}}
                for r in records]


def load(store: EventStore, all_events: dict[str, list[dict]]) -> list[dict]:
    """Import any finding events the store lacks, then return the revisions as finding events."""
    ks = KnowledgeStore(store.root)
    try:
        ks.import_events(all_events)
    except OSError:
        pass  # a read-only store still shows what the store holds
    return ks.as_events(ks.read())
