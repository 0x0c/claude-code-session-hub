"""The knowledge store: one durable record per revision of a knowledge entry.

The event store keeps a short `finding` notice on the timeline; the full text of the finding lives
here, under `<store>/knowledge/`. Each file has one writer, as in the event store, so sharing the
store through Git never produces a merge conflict: `<session-id>.jsonl` for a sub-session and
`<session-id>@<writer>.jsonl` for the parent. The copies of events that predate the store go to
`<session-id>@migrated.jsonl`, a file of their own, so that a machine that migrates never writes a
live writer's file. Machines that migrate the same events write the same lines, and read() skips a
duplicate; clones that migrated different events can still conflict on this one transitional file.

A line is one revision of one entry. The entry is named by a short hash of the finding's key (the
title when no key is given), so two sessions that report the same caveat append to the same entry.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from . import collections
from .store import EventStore, _check_id

MIGRATED = "migrated"  # the writer name of the file that holds the copied legacy events
FIELDS = ("kind", "title", "body", "tags", "scope", "key", "status")
NOTICE_FIELDS = ("kind", "title", "key", "status")  # what the timeline event keeps


class Unwritable(OSError):
    """The knowledge store cannot take a record from this writer; a retry will not help by itself."""


def entry_id(finding: dict) -> str:
    """Name an entry by a short hash of its normalized key (or title)."""
    return collections.entry_id(finding.get("key") or finding.get("title") or "")


def notice(finding: dict) -> dict:
    """Return the part of a finding that stays on the timeline.

    The `stored` mark says that the full text is in the knowledge store, so that a reader never
    mistakes the notice for an old event whose text still has to be copied.
    """
    return {**{k: finding[k] for k in NOTICE_FIELDS if k in finding}, "stored": True}


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
        path = self._path(session_id, writer)
        while True:
            f = open(path, "a", encoding="utf-8")
            fcntl.flock(f, fcntl.LOCK_EX)
            if os.fstat(f.fileno()).st_nlink > 0:
                break
            # delete_session() unlinked the file while we waited for the lock; reopen the path so
            # that the record lands in a fresh file instead of vanishing with the unlinked one
            fcntl.flock(f, fcntl.LOCK_UN)
            f.close()
        with f:
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

    def ensure_writable(self, session_id: str, writer: str | None = None) -> None:
        """Raise OSError when the store cannot take a record from this writer, so that a writer fails
        before it puts a notice on the timeline whose text it could not keep. A full disk is beyond
        the check."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            if not os.access(self.dir, os.W_OK):
                raise PermissionError(f"the knowledge store is not writable: {self.dir}")
            open(self._path(session_id, writer), "a", encoding="utf-8").close()  # the writer's own file, too
        except OSError as e:
            raise Unwritable(str(e)) from e

    def read(self) -> list[dict]:
        """Return every revision record in time order; a corrupt line is skipped."""
        out, seen = [], set()
        for path in sorted(self.dir.glob("*.jsonl")) if self.dir.exists() else []:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        key = (rec["event_id"], rec["entry"])
                        if not all(isinstance(rec.get(k), str) for k in ("title", "ts", "session_id", "event_id", "entry")):
                            continue
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
                    # A hand edit or a Git merge can leave a field of the wrong type; drop that field
                    # rather than let one line stop every snapshot
                    for k in ("kind", "body", "scope", "key", "status"):
                        if k in rec and not isinstance(rec[k], str):
                            del rec[k]
                    if not (isinstance(rec.get("tags", []), list) and all(isinstance(t, str) for t in rec.get("tags", []))):
                        del rec["tags"]
                    if key in seen:  # a duplicate line from a Git merge
                        continue
                    seen.add(key)
                    out.append(rec)
        out.sort(key=lambda r: (r["ts"], r["event_id"]))
        return out

    def legacy(self, all_events: dict[str, list[dict]], records: list[dict] | None = None) -> list[dict]:
        """Return the revisions of finding events that predate the store and that it does not hold.

        Such an event carries the full text and has no `stored` mark; a notice that a writer is
        about to match with its record has the mark, so it never counts as legacy.
        """
        known = {r["event_id"] for r in (self.read() if records is None else records)}
        return [self._record(ev, ev["finding"]) for evs in all_events.values() for ev in evs
                if ev["type"] == "finding" and ev.get("finding") and not ev["finding"].get("stored")
                and ev["id"] not in known]

    def import_events(self, all_events: dict[str, list[dict]]) -> int:
        """Copy the legacy finding events into the store; return how many were copied.

        A second run copies nothing, because the copies are known by then. The copies go to one
        `<session-id>@migrated.jsonl` per session; each record keeps the writer that reported it.
        """
        fresh: dict[str, list[dict]] = {}
        for rec in self.legacy(all_events):
            fresh.setdefault(rec["session_id"], []).append(rec)
        for sid, recs in fresh.items():
            self._append_lines(sid, MIGRATED, recs)
        return sum(len(r) for r in fresh.values())

    @staticmethod
    def as_events(records: list[dict]) -> list[dict]:
        """Shape revision records like finding events, so that a collection can project them."""
        return [{"id": r["event_id"], "session_id": r["session_id"], "writer": r.get("writer"), "seq": 0,
                 "ts": r["ts"], "type": "finding", "finding": {k: r[k] for k in FIELDS if k in r}}
                for r in records]


def load(store: EventStore, all_events: dict[str, list[dict]]) -> list[dict]:
    """Return the revisions as finding events, legacy events included; this never writes.

    Reading must not write: a reader on another machine would otherwise create files that belong to
    other writers. The server copies the legacy events once, with migrate(), when it starts.
    """
    ks = KnowledgeStore(store.root)
    records = ks.read()
    return ks.as_events(sorted(records + ks.legacy(all_events, records), key=lambda r: (r["ts"], r["event_id"])))


def migrate(store: EventStore) -> int:
    """Copy the finding events that predate the store into it; return how many were copied."""
    try:
        return KnowledgeStore(store.root).import_events(store.read_all())
    except OSError:
        return 0  # a read-only store keeps working: load() still shows the legacy events
