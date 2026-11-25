"""The knowledge store: the full text of every finding lives under <store>/knowledge/."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_migrated_copies_go_to_their_own_file_and_keep_the_writer(self):
        self.store.append("a", {"type": "finding", "finding": {"kind": "caveat", "title": "Old", "body": "kept"}}, writer="parent")
        knowledge_store.migrate(self.store)
        files = sorted(p.name for p in (self.store.root / "knowledge").glob("*.jsonl"))
        self.assertEqual(files, ["a@migrated.jsonl"])  # never a@parent.jsonl, which another machine may write
        self.assertEqual(self.ks.read()[0]["writer"], "parent")
        self.store.delete_session("a")
        self.assertEqual(list((self.store.root / "knowledge").glob("*.jsonl")), [])

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

    @unittest.skipIf(os.geteuid() == 0, "root can write to any file")
    def test_a_read_only_writer_file_fails_before_the_notice(self):
        self.learn("a", kind="caveat", title="first", body="b")
        path = self.store.root / "knowledge" / "a.jsonl"
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        before = self.store.read("a")
        with self.assertRaises(OSError):
            self.learn("a", kind="caveat", title="second", body="b")
        self.assertEqual(self.store.read("a"), before)  # no notice stayed behind

    @unittest.skipIf(os.geteuid() == 0, "root can write to any file")
    def test_the_hub_answers_507_when_the_knowledge_store_cannot_take_a_record(self):
        import threading
        from session_hub import client
        from session_hub.server import make_server
        self.learn("a", kind="caveat", title="first", body="b")
        path = self.store.root / "knowledge" / "a.jsonl"
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        srv, _ = make_server(self.store, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        with self.assertRaises(ValueError) as cm:  # not PushError: the outbox would retry it forever
            client.post(url, {"session_id": "a", "fields": {"type": "finding", "finding": {"kind": "caveat", "title": "second", "body": "b"}}}, token=None)
        self.assertIn("could not store", str(cm.exception))

    @unittest.skipIf(os.geteuid() == 0, "root can write to any file")
    def test_an_outbox_event_survives_a_507_and_a_live_send_fails_cleanly(self):
        import io, threading
        from contextlib import redirect_stderr
        from session_hub import cli, client
        from session_hub.server import make_server
        self.learn("a", kind="caveat", title="first", body="b")
        path = self.store.root / "knowledge" / "a.jsonl"
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        srv, _ = make_server(self.store, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        outbox = Path(self._tmp.name) / "outbox.jsonl"
        payload = {"session_id": "a", "fields": {"type": "finding", "finding": {"kind": "caveat", "title": "queued", "body": "b"}}}
        with mock.patch.dict(os.environ, {"HUB_OUTBOX": str(outbox)}):
            client.spool(payload)
            client.spool({"session_id": "b", "fields": {"type": "report", "summary": "later"}})
            self.assertEqual(client.flush(url), 1)  # the report goes ahead; only the finding waits
            self.assertTrue(outbox.exists())  # kept: the store may be fixed later
            self.assertEqual([json.loads(ln)["session_id"] for ln in outbox.read_text().splitlines()], ["a"])
            self.assertEqual([e["type"] for e in self.store.read("b")], ["report"])
            with mock.patch.dict(os.environ, {"HUB_URL": url, "HUB_SESSION_ID": "a"}), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                cli.main(["learn", "--kind", "caveat", "--title", "live", "--body", "b"])
        self.assertIn("507", str(cm.exception.code))
        self.assertEqual(len(outbox.read_text().splitlines()), 1)  # the live event was not spooled behind it

    def test_another_write_failure_answers_500_and_stays_retryable(self):
        import threading
        from session_hub import client
        from session_hub.server import make_server
        srv, hub = make_server(self.store, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        with mock.patch.object(type(self.store), "append", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(client.PushError) as cm:  # the outbox keeps it: a full disk can heal
                client.post(url, {"session_id": "a", "fields": {"type": "report", "summary": "x"}})
        self.assertIn("500", str(cm.exception))

    def test_a_full_disk_in_the_preflight_stays_retryable(self):
        import errno
        with mock.patch.object(Path, "mkdir", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with self.assertRaises(OSError) as cm:
                self.ks.ensure_writable("a")
        self.assertNotIsInstance(cm.exception, knowledge_store.Unwritable)  # the hub answers 500, not 507

    def test_a_failure_after_the_notice_fails_loudly_through_the_hub(self):
        import errno, threading
        from session_hub import client
        from session_hub.server import make_server
        srv, _ = make_server(self.store, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        full = OSError(errno.ENOSPC, "No space left on device")
        with mock.patch.object(knowledge_store.KnowledgeStore, "append", side_effect=full):
            with self.assertRaises(client.StoreError) as cm:  # not PushError: no quiet outbox, no duplicate notice
                client.post(url, {"session_id": "a", "fields": {"type": "finding", "finding": {"kind": "caveat", "title": "t", "body": "b"}}})
        self.assertIn("could not be stored", str(cm.exception))

    def test_a_hook_survives_a_store_that_cannot_take_an_event(self):
        import io
        from contextlib import redirect_stderr
        from session_hub import client, hooks
        with mock.patch.object(hooks, "current_session_id", return_value="a"):
            with mock.patch.object(hooks, "deliver", side_effect=client.StoreError("507")):
                self.assertIsNone(hooks.send({"type": "report"}))
        with mock.patch.object(hooks, "_read_payload", return_value={}), \
                mock.patch.dict(hooks.HANDLERS, {"stop": mock.Mock(side_effect=PermissionError("read-only"))}), \
                redirect_stderr(io.StringIO()) as err:
            hooks.run("stop")  # prints to stderr and returns; the session is not stopped
        self.assertIn("read-only", err.getvalue())

    def test_a_record_survives_a_deletion_that_ran_while_it_waited_for_the_lock(self):
        ev = self.learn("a", kind="caveat", title="first", body="b")
        path = self.store.root / "knowledge" / "a.jsonl"
        real_flock, unlinked = knowledge_store.fcntl.flock, []

        def flock(f, op):
            real_flock(f, op)
            if not unlinked:  # the first lock is taken just as delete_session unlinks the file
                unlinked.append(path.unlink())

        with mock.patch.object(knowledge_store.fcntl, "flock", flock):
            self.ks.append(ev, {"kind": "caveat", "title": "second", "body": "kept"})
        self.assertEqual([r["title"] for r in self.ks.read()], ["second"])  # in the new file, not the unlinked one

    def test_a_stored_notice_without_a_record_shows_nothing(self):
        # An event that claims "stored" but has no record is not an old event, so nothing copies it:
        # the notice can mean that its record has not arrived yet
        self.store.append("a", {"type": "finding", "finding": {"kind": "caveat", "title": "Claim", "body": "x", "stored": True}})
        self.assertEqual(self.items(), [])
        self.assertEqual(knowledge_store.migrate(self.store), 0)

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

    def test_a_field_of_the_wrong_type_is_dropped_and_the_snapshot_builds(self):
        ev = self.learn("a", kind="caveat", title="t", body="b", scope="s/")
        path = self.store.root / "knowledge" / "a.jsonl"
        bad = {**json.loads(path.read_text().splitlines()[0]), "event_id": "a#9", "ts": "2999-01-01T00:00:00.000Z",
               "scope": ["q"], "tags": [["x"]], "kind": 3}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(bad) + "\n")
        (item,) = self.items()
        self.assertEqual((item["count"], item["scopes"], item["tags"]), (2, ["s/"], []))

    def test_a_custom_collection_of_findings_reads_the_text_too(self):
        defs = [{"name": "decisions", "match": {"type": ["finding"], "kind": ["decision"]},
                 "reduce": {"type": "log", "payload": "finding"}, "view": {"type": "table"}}]
        self.learn("a", kind="decision", title="Limit", body="120 per minute")
        snap = view.store_snapshot(self.store, defs=[collections._validate(d) for d in defs])
        self.assertEqual(snap["collections"]["decisions"]["items"][0]["body"], "120 per minute")

    def test_the_hub_publishes_a_record_that_lands_after_its_notice(self):
        from session_hub.server import Hub
        hub = Hub(self.store)
        ev = self.store.append("a", {"type": "finding", "finding": {"kind": "caveat", "title": "Late", "stored": True}})
        hub.publish()
        sent = []
        hub._broadcast = lambda event, data: sent.append(event)
        self.ks.append(ev, {"kind": "caveat", "title": "Late", "body": "the text"})
        self.assertTrue(hub.publish())  # no event changed, and the collection did
        self.assertEqual(sent, ["update"])
        self.assertEqual(hub.snap["collections"]["knowledge"]["items"][0]["body"], "the text")

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

    def test_deleting_a_session_deletes_the_knowledge_it_recorded(self):
        self.learn("a", kind="caveat", title="Shared", body="from a")
        self.learn("a", kind="insight", title="Mine", body="secret text", writer="parent")
        self.learn("b", kind="caveat", title="Shared", body="from b")
        self.assertGreater(self.store.delete_session("a"), 0)
        self.assertEqual(sorted(p.name for p in (self.store.root / "knowledge").glob("*.jsonl")), ["b.jsonl"])
        (item,) = self.items()
        self.assertEqual((item["title"], item["body"], item["reporters"]), ("Shared", "from b", ["b"]))

    def test_deleting_a_session_with_only_knowledge_files_reports_them(self):
        ev = self.learn("a", kind="caveat", title="t", body="b")
        (self.store.root / "events" / "a.jsonl").unlink()
        self.assertEqual(self.store.delete_session("a"), 1)
        self.assertFalse((self.store.root / "knowledge" / "a.jsonl").exists())

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
