"""The knowledge store: the full text of every finding lives under <store>/knowledge/."""

import json
import tempfile
import unittest
from pathlib import Path

from session_hub import collections, core, knowledge_store, schema, view
from session_hub.store import EventStore


class KnowledgeStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = EventStore(Path(self._tmp.name) / "store")
        self.ks = knowledge_store.KnowledgeStore(self.store.root)

    def learn(self, sid, writer=None, **finding):
        return core.record(self.store, sid, {"type": "finding", "finding": finding}, writer=writer)["event"]

    def items(self):
        return view.store_snapshot(self.store)["collections"]["knowledge"]["items"]

    def test_the_timeline_keeps_a_notice_and_the_store_keeps_the_text(self):
        ev = self.learn("a", kind="caveat", title="Redis SCAN", body="cursor restarts", tags=["Redis"], scope="search/")
        notice = self.store.read("a")[0]["finding"]
        self.assertEqual((notice["title"], notice["kind"], notice.get("body"), notice.get("scope"), notice["tags"]),
                         ("Redis SCAN", "caveat", None, None, []))
        (rec,) = self.ks.read()
        self.assertEqual((rec["event_id"], rec["body"], rec["tags"], rec["scope"]), (ev["id"], "cursor restarts", ["redis"], "search/"))
        self.assertTrue((self.store.root / "knowledge" / "a.jsonl").exists())

    def test_sessions_that_report_the_same_item_share_one_entry_with_a_history(self):
        self.learn("a", kind="caveat", title="Redis SCAN", body="first wording")
        self.learn("b", kind="caveat", title="Redis SCAN", body="first wording")  # same words: no new revision
        self.learn("b", kind="caveat", title="Redis SCAN", body="second wording")
        (item,) = self.items()
        self.assertEqual((item["count"], item["reporters"], item["body"]), (3, ["a", "b"], "second wording"))
        self.assertEqual([h["body"] for h in item["history"]], ["first wording", "second wording"])
        self.assertEqual(item["entry"], collections.entry_id("Redis SCAN"))
        self.assertEqual(len(item["entry"]), 10)

    def test_a_key_names_the_entry_instead_of_the_title(self):
        self.learn("a", kind="decision", title="Limit is 120", key="limit")
        self.learn("a", kind="decision", title="Limit is 90", key="limit")
        (item,) = self.items()
        self.assertEqual((item["title"], item["entry"]), ("Limit is 90", collections.entry_id("limit")))

    def test_obsolete_status_is_a_revision(self):
        self.learn("a", kind="caveat", title="x", body="b")
        self.learn("a", kind="caveat", title="x", body="b", status="obsolete")
        (item,) = self.items()
        self.assertEqual((item["status"], len(item["history"])), ("obsolete", 2))

    def test_the_parent_writes_its_own_file(self):
        self.learn("a", kind="insight", title="t", writer="parent")
        self.assertTrue((self.store.root / "knowledge" / "a@parent.jsonl").exists())
        self.assertEqual(self.ks.read()[0]["writer"], "parent")

    def old_event(self):
        # An old event carries the full text, as every event did before the knowledge store existed
        return self.store.append("a", {"type": "finding", "finding": {"kind": "caveat", "title": "Old", "body": "kept", "tags": ["x"]}})

    def test_reading_shows_old_events_and_writes_nothing(self):
        self.old_event()
        (item,) = self.items()
        self.assertEqual((item["body"], item["tags"]), ("kept", ["x"]))
        self.assertEqual(self.ks.read(), [])
        self.assertFalse((self.store.root / "knowledge").exists())

    def test_migrating_copies_old_events_once(self):
        self.old_event()
        self.assertEqual(knowledge_store.migrate(self.store), 1)
        self.assertEqual(knowledge_store.migrate(self.store), 0)
        self.assertEqual(len(self.ks.read()), 1)
        (item,) = self.items()
        self.assertEqual((item["body"], item["count"]), ("kept", 1))  # shown once, not as a copy and an event

    def test_a_snapshot_between_the_notice_and_its_record_loses_no_text(self):
        notice = {"type": "finding", "finding": {"kind": "caveat", "title": "Race", "stored": True}}
        ev = self.store.append("a", notice)  # core.record has written the notice, and not yet the record
        knowledge_store.migrate(self.store)
        self.items()
        self.ks.append(ev, {"kind": "caveat", "title": "Race", "body": "the text"})
        (item,) = self.items()
        self.assertEqual(item["body"], "the text")

    def test_a_store_that_cannot_take_a_record_fails_before_the_notice(self):
        self.store.root.mkdir(parents=True)
        (self.store.root / "knowledge").write_text("a file where the directory should be")
        with self.assertRaises(OSError):
            self.learn("a", kind="caveat", title="t", body="b")
        self.assertEqual(self.store.read_all(), {})  # no notice stayed behind

    def test_a_change_under_knowledge_changes_the_signature(self):
        ev = self.learn("a", kind="caveat", title="t", body="b")
        before = self.store.signature()
        self.ks.append(ev, {"kind": "caveat", "title": "t", "body": "again"})
        self.assertNotEqual(self.store.signature(), before)

    def test_a_corrupt_file_does_not_break_reading(self):
        self.learn("a", kind="caveat", title="t", body="b")
        (self.store.root / "knowledge" / "bad.jsonl").write_bytes(b'\xff\xfe not json\n{"entry":"e","event_id":"x","ts":null,"title":"t","session_id":"s"}\n')
        self.assertEqual(len(self.ks.read()), 1)
        self.assertEqual(len(self.items()), 1)

    def test_a_custom_collection_of_findings_reads_the_text_too(self):
        defs = [{"name": "decisions", "match": {"type": ["finding"], "kind": ["decision"]},
                 "reduce": {"type": "log", "payload": "finding"}, "view": {"type": "table"}}]
        self.learn("a", kind="decision", title="Limit", body="120 per minute")
        snap = view.store_snapshot(self.store, defs=[collections._validate(d) for d in defs])
        self.assertEqual(snap["collections"]["decisions"]["items"][0]["body"], "120 per minute")

    def test_the_hub_migrates_when_it_starts(self):
        from session_hub.server import Hub
        self.old_event()
        Hub(self.store)
        self.assertEqual(len(self.ks.read()), 1)

    def test_a_corrupt_or_duplicated_line_is_skipped(self):
        self.learn("a", kind="insight", title="t", body="b")
        path = self.store.root / "knowledge" / "a.jsonl"
        line = path.read_text(encoding="utf-8")
        path.write_text("not json\n" + line + line + '{"entry": "x"}\n', encoding="utf-8")
        self.assertEqual(len(self.ks.read()), 1)

    def test_an_unsafe_session_id_is_refused(self):
        with self.assertRaises(schema.SchemaError):
            self.ks.append({"id": "x", "session_id": "../evil", "ts": "2026-01-01T00:00:00.000Z"}, {"title": "t"})
        self.assertFalse((self.store.root.parent / "evil.jsonl").exists())

    def test_the_knowledge_survives_deleting_the_session(self):
        self.learn("a", kind="caveat", title="t", body="b")
        self.store.delete_session("a")
        (item,) = self.items()
        self.assertEqual(item["body"], "b")

    def test_the_cli_reads_the_text_from_the_store(self):
        self.learn("a", kind="caveat", title="Redis SCAN", body="cursor restarts", tags=["redis"])
        lines = view.knowledge_lines(view.store_snapshot(self.store), with_body=True)
        self.assertEqual(lines, ["[caveat] Redis SCAN (#redis)\n    cursor restarts"])

    def test_the_markdown_sink_still_renders_the_text(self):
        self.learn("a", kind="caveat", title="Redis SCAN", body="cursor restarts")
        snap = view.store_snapshot(self.store)
        self.assertIn("cursor restarts", collections.render_markdown(snap["collections"]["knowledge"]))


if __name__ == "__main__":
    unittest.main()
