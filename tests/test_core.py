"""The schema, the views, the collections, the store, and the hub, below the level of the commands."""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest import mock

from session_hub import collections, core, desktop, schema, session_name, store as store_module, usage, view
from session_hub.server import Hub, make_server
from session_hub.store import EventStore


class TmpCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.store = EventStore(self.dir / "store")

    def record(self, sid, writer=None, **fields):
        return core.record(self.store, sid, fields, writer=writer)["status"]


class SchemaTest(unittest.TestCase):
    def event(self, **fields):
        return schema.normalize_event({"session_id": "s", "seq": 1, "ts": "2026-01-01T00:00:00.000Z", "type": "report",
                                       **fields})

    def test_required_fields(self):
        for key in ("session_id", "seq", "ts", "type"):
            with self.subTest(key), self.assertRaisesRegex(schema.SchemaError, f"{key} is required"):
                self.event(**{key: None})

    def test_invalid_values(self):
        for fields in ({"seq": 0}, {"seq": "1"}, {"actor": "x"}, {"confidence": "x"}, {"type": "ask"},
                       {"type": "answer"}, {"type": "finding"}, {"type": "finding", "finding": {"title": ""}},
                       {"type": "finding", "finding": {"title": "t", "kind": "x"}},
                       {"type": "finding", "finding": {"title": "t", "tags": "x"}},
                       {"tasks": [{"t": "a", "s": "x"}]}, {"tasks": [{"t": "a", "size": "x"}]},
                       {"attention": {"kind": "x"}}, {"ts": "bad"}, {"ts": 1}, {"ts": "2026-01-01T00:00:00"},
                       {"tasks": None}, {"tasks": "x"}, {"tasks": ["x"]}, {"tasks": [{}]}, {"tasks": [{"t": ""}]},
                       {"tasks": [{"t": "   "}]}, {"type": "finding", "finding": {"title": "  "}}):
            with self.subTest(fields), self.assertRaises(schema.SchemaError):
                self.event(**fields)

    def test_the_input_is_not_modified(self):
        tasks = [{"t": "x" * 99}]
        self.assertEqual(len(self.event(tasks=tasks)["tasks"][0]["t"]), schema.LIMITS["task"])
        self.assertEqual(tasks, [{"t": "x" * 99}])

    def test_finding_is_normalized(self):
        f = self.event(type="finding", finding={"title": " a  b ", "body": "x  y\n\n\n\nz", "extra": 1,
                                                "tags": ["B", "b", " ", "a"]})["finding"]
        self.assertEqual(f, {"kind": "insight", "title": "a b", "body": "x y\n\nz", "tags": ["a", "b"],
                             "status": "active"})

    def test_iso_after_crosses_a_day(self):
        self.assertEqual(schema.iso_after("2026-12-31T23:59:59.999Z"), "2027-01-01T00:00:00.000Z")

    def test_fold_needs_an_event(self):
        with self.assertRaises(schema.SchemaError):
            schema.fold([])

    def test_every_gate_condition_has_a_message(self):
        st = schema.empty_status("s")
        st["pr"] = {"number": 1, "mergeable": False, "unresolved_threads": 2}
        st["attention"] = {"qid": 1}
        st["tasks"] = [{"t": t, "s": "todo", "size": "M"} for t in "abcd"]
        self.assertEqual(schema.ready_gate(st), [
            "CI: unknown", "merge conflict", "2 open threads", "unanswered question", "self-review not done",
            "tests not added", "no PR description", "tasks left: a, b, c…"])


class CoreTest(TmpCase):
    def test_task_updates_must_be_strings(self):
        for updates in ("a=done", [1]):
            with self.assertRaises(schema.SchemaError):
                self.record("s", type="report", task_updates=updates)
        self.assertEqual(self.store.read("s"), [])

    def test_a_task_keeps_what_the_update_leaves_out(self):
        self.assertEqual(core.merge_tasks([{"t": "a", "s": "doing", "size": "L"}], ["a", "a=:S", "b"]),
                         [{"t": "a", "s": "doing", "size": "S"}, {"t": "b", "s": "todo", "size": "M"}])

    def test_an_answer_to_another_question_changes_nothing(self):
        self.record("s", type="ask", attention={"kind": "decision", "question": "q?"})
        st = self.record("s", writer="parent", type="answer", actor="parent", qid=99, value="x")
        self.assertEqual((st["state"], st["attention"]["qid"]), ("needs_human", 1))

    def test_moving_on_closes_the_question(self):
        self.record("s", type="ask", attention={"kind": "decision", "question": "q?"})
        self.assertIsNone(self.record("s", type="report", state="working")["attention"])


class ViewTest(TmpCase):
    def snap(self, **kw):
        return view.snapshot(self.store.read_all(), **kw)

    def later(self, minutes):
        return datetime.now(timezone.utc) + timedelta(minutes=minutes, seconds=1)

    def test_attention_lines(self):
        self.record("ask", type="ask", task_ref="#1", attention={
            "kind": "decision", "question": "q?", "options": ["x", "y"], "default": "x"})
        self.record("fail", type="fail", summary="sum")
        self.record("work", type="start", state="working")
        self.record("ready", type="start", pr={"number": 4, "ci": "pass"})
        self.record("ready", type="ready", summary="look",
                    ready={"self_review": True, "tests_added": True, "description": True})
        now = self.later(45)
        lines = view.attention_lines(self.snap(now=now), now)
        self.assertEqual(lines, ['NH ask #1 decision q=1 "q?" [x*|y] 45m', "FL fail sum", "RR ready PR#4 ci=pass look",
                                 "ST work 45m since heartbeat"])
        self.assertTrue(all("work" not in ln for ln in view.attention_lines(self.snap())))

    def test_a_review_that_fails_the_gate_asks_for_nothing(self):
        self.record("s", type="ready", ready={})
        self.assertFalse(self.snap()["sessions"][0]["needs_action"])

    def test_the_stale_limit(self):
        self.record("s", type="start", state="working")
        evs = self.store.read("s")
        for minutes, want in ((29, False), (30, True)):
            self.assertIs(view.session_view(evs, self.later(minutes))[0]["stale"], want)

    def test_state_code(self):
        self.assertEqual(view.state_code({"stale": False, "state": "done"}), "OK")  # An older hub: no "archived"
        self.assertEqual(view.state_code({"stale": True, "state": "working", "archived": None}), "ST")
        self.assertEqual(view.state_code({"stale": False, "state": "done", "archived": {"by": "x"}}), "AR")
        self.assertEqual(view.state_code({"stale": False, "state": "new"}), "??")
        self.assertEqual(set(view.ICON), set(schema.STATES))

    def test_ago(self):
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.assertEqual([view._ago(ts, now) for ts in (None, "2026-01-01T22:01:00Z", "2026-01-01T21:00:00Z")],
                         ["-", "119m", "3h"])

    def test_timeline_lines(self):
        self.record("s", type="start", phase="plan", tasks=[{"t": "a", "s": "done"}])
        self.record("s", type="ask", summary="hidden", attention={"kind": "decision", "question": "q?"})
        self.record("s", type="heartbeat", actor="hook")
        self.record("s", writer="parent", type="archive", actor="parent")
        self.record("s", writer="parent", type="unarchive", actor="parent")
        lines = [ln.split(" ", 1)[1] for ln in view.timeline_lines(self.snap(), "s")]
        self.assertEqual(len(lines), 4)
        self.assertIn("s [child] start", lines[0])
        for change in ("state:queued→planning", "phase:None→plan", "tasks:1/1"):
            self.assertIn(change, lines[0])
        self.assertTrue(lines[1].endswith("q?"))
        self.assertIn("[parent] archive   archived", lines[2])
        self.assertIn("unarchived", lines[3])
        self.assertEqual(view.timeline_lines(self.snap(), "other"), [])

    def test_the_totals_sum_every_session(self):
        for sid, cost in (("a", 0.1), ("b", 0.2)):
            self.record(sid, type="heartbeat", usage={"cost_usd": cost, "input": 5, "output": None})
        self.assertEqual(self.snap()["total"], {"cost_usd": 0.3, "input": 10, "output": 0})

    def test_knowledge_filters(self):
        for title, kind, tags, scope in (("one", "caveat", ["ci"], "tests/a.py"), ("two", "howto", ["dev"], None)):
            self.record("s", type="finding", finding={"kind": kind, "title": title, "tags": tags, "scope": scope})
        self.record("t", type="finding", finding={"kind": "caveat", "title": "one"})
        snap = self.snap()
        names = lambda **kw: [ln.split()[1] for ln in view.knowledge_lines(snap, **kw)]  # noqa: E731
        self.assertEqual(names(), ["one", "two"])
        self.assertEqual(names(kinds=["howto"]), ["two"])
        self.assertEqual(names(tags=["ci"]), ["one"])
        self.assertEqual(names(scope="tests/"), ["one"])  # A folder finds the files in it, and the reverse
        self.assertEqual(names(scope="tests/a.py::T"), ["one"])
        self.assertEqual(names(limit=1), ["one"])
        self.assertEqual(names(name="nope"), [])
        self.assertIn("x2", view.knowledge_lines(snap)[0])


class CollectionTest(unittest.TestCase):
    EVENTS = [{"id": f"{sid}#{i}", "session_id": sid, "ts": f"2026-01-01T00:00:0{i}Z", "type": "report", "summary": s,
               "diff": {}, "tags": [s]} for i, (sid, s) in enumerate((("a", "x"), ("b", "y"), ("a", "z")), 1)]

    def project(self, reduce, match=None):
        return collections.project(collections._validate({"name": "c", "reduce": reduce, "match": match or {}}),
                                   self.EVENTS)

    def test_latest_keeps_the_newest_event_per_key(self):
        items = self.project({"type": "latest", "key": ["session_id"]})
        self.assertEqual([(i["key"], i["summary"], i["count"]) for i in items], [("a", "z", 2), ("b", "y", 1)])
        self.assertEqual((items[0]["first_ts"][-2], items[0]["last_ts"][-2]), ("1", "3"))
        self.assertNotIn("diff", items[0])

    def test_log_lists_every_event(self):
        self.assertEqual([i["key"] for i in self.project({"type": "log"})], ["a#3", "b#2", "a#1"])

    def test_aggregate_merges_tags_and_reporters(self):
        item, = self.project({"type": "aggregate", "key": ["type"]})
        self.assertEqual((item["tags"], item["reporters"], item["count"]), (["x", "y", "z"], ["a", "b"], 3))

    def test_match_conditions(self):
        for match, want in (({"type": ["ask"]}, 0), ({"session": ["a"]}, 2), ({"tags_any": ["y"]}, 1),
                            ({"kind": ["x"]}, 0), ({"status": ["obsolete"]}, 0), ({"status": ["active"]}, 3)):
            with self.subTest(match):
                self.assertEqual(len(self.project({"type": "log"}, match)), want)

    def test_the_key_falls_back(self):
        self.assertEqual(collections._key({"id": "e"}, {"key": "", "title": " A　 b "}, ["key|title"]), "a b")
        self.assertEqual(collections._key({"id": "e"}, {}, []), "e")

    def test_a_user_file_overrides_and_disables(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "collections.json"
            path.write_text(json.dumps({"collections": [{"name": "knowledge", "label": "K"}, {"name": "extra"}]}))
            defs = {d["name"]: d for d in collections.load_definitions(Path(tmp))}
            self.assertEqual((defs["knowledge"]["label"], defs["knowledge"]["view"]["type"]), ("K", "cards"))
            self.assertEqual(defs["extra"]["view"]["type"], "table")
            path.write_text(json.dumps([{"name": "knowledge", "enabled": False}]))
            self.assertEqual(collections.load_definitions(Path(tmp)), [])

    def test_sinks_rewrite_changed_files_and_stay_in_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = collections._validate({"name": "c", "sinks": [{"type": "jsonl", "path": "sub/c.jsonl"}]})
            cols = collections.project_all([d], self.EVENTS)
            out, = collections.write_sinks([d], cols, Path(tmp))
            self.assertEqual(len(out.read_text().splitlines()), 3)
            self.assertEqual(collections.write_sinks([d], cols, Path(tmp)), [])
            d["sinks"][0]["path"] = "../out.jsonl"
            with self.assertRaises(collections.CollectionError):
                collections.write_sinks([d], cols, Path(tmp))

    def test_markdown_without_groups(self):
        d = collections._validate({"name": "c"})
        text = collections.render_markdown(collections.project_all([d], self.EVENTS)["c"], {"a": "Alpha"}, "xx")
        self.assertIn("# c\n", text)
        self.assertIn("### z", text)
        self.assertIn("Reported by Alpha (1 reports", text)
        self.assertNotIn("\n## ", text)

    def test_localized_falls_back(self):
        self.assertEqual(collections.localized({"en": "E"}, "ja"), "E")
        self.assertEqual(collections.localized({"fr": "F"}, "ja"), "F")
        self.assertEqual(collections.localized({}, "ja"), "")


class StoreTest(TmpCase):
    def test_the_session_id_sources(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "local"}, clear=True):
            self.assertEqual(store_module.current_session_id(), "local")
            os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_1"
            self.assertEqual(store_module.current_session_id(), "session_1")
            os.environ["CLAUDE_CODE_REMOTE_SESSION_ID"] = "other"
            self.assertEqual(store_module.current_session_id(), "other")
            os.environ["HUB_SESSION_ID"] = "hub"
            self.assertEqual(store_module.current_session_id(), "hub")

    def test_unsafe_ids_are_refused(self):
        for sid in ("", "a/b", "..\\x", "a@b", "a b", "x" * 129):
            with self.subTest(sid), self.assertRaises(schema.SchemaError):
                self.store.append(sid, {"type": "start"})
        with self.assertRaises(schema.SchemaError):
            self.store.append("a", {"type": "start"}, writer="../x")

    def test_a_session_does_not_see_another_with_the_same_prefix(self):
        self.store.append("a", {"type": "start"})
        self.store.append("ab", {"type": "start"})
        self.assertEqual(self.store.delete_session("a"), 1)
        self.assertEqual(self.store.session_ids(), ["ab"])

    def test_the_sequence_continues_after_a_corrupt_line(self):
        self.store.append("a", {"type": "start"})
        with open(self.store.events_dir / "a.jsonl", "a") as f:
            f.write("not json\n[1]\n\n")
        self.assertEqual(self.store.append("a", {"type": "report"})["seq"], 2)
        self.assertEqual([e["seq"] for e in self.store.read("a")], [1, 2])

    def test_an_invalid_event_does_not_hide_the_others(self):
        self.store.append("a", {"type": "start"})
        with open(self.store.events_dir / "a.jsonl", "a") as f:
            for seq, fields in enumerate(({"ts": "bad"}, {"ts": "2026-01-01T00:00:00"}, {"tasks": [{}]}), 2):
                f.write(json.dumps({"session_id": "a", "seq": seq, "ts": "2026-01-01T00:00:00Z", "type": "report",
                                    **fields}) + "\n")
        self.store.append("b", {"type": "start"})
        self.assertEqual([s["session_id"] for s in view.snapshot(self.store.read_all())["sessions"]], ["a", "b"])
        self.assertEqual([e["seq"] for e in self.store.read("a")], [1])

    def test_concurrent_writers_get_distinct_numbers_and_times(self):
        threads = [threading.Thread(target=lambda: [self.store.append("a", {"type": "report"}) for _ in range(20)])
                   for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        evs = self.store.read("a")
        self.assertEqual([e["seq"] for e in evs], list(range(1, 81)))
        self.assertEqual(len({e["ts"] for e in evs}), 80)

    def test_time_moves_forward_when_the_clock_goes_back(self):
        with mock.patch.object(schema, "now_iso", side_effect=["2026-01-01T00:00:00.005Z", "2026-01-01T00:00:00.001Z"]):
            first, second = (self.store.append("a", {"type": "report"})["ts"] for _ in range(2))
        self.assertEqual((first, second), ("2026-01-01T00:00:00.005Z", "2026-01-01T00:00:00.006Z"))

    def test_the_signature_follows_the_files(self):
        self.assertEqual(self.store.signature(), ())
        self.store.append("a", {"type": "start"})
        before = self.store.signature()
        self.store.append("a", {"type": "report"})
        self.assertNotEqual(self.store.signature(), before)


class GitStoreTest(TmpCase):
    def git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True)

    def clone(self, name):
        root = self.dir / name
        self.git("clone", "-q", str(self.dir / "remote.git"), str(root))
        for key, value in (("user.name", "t"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
            self.git("-C", str(root), "config", key, value)
        return EventStore(root)

    def test_a_plain_folder_is_not_synced(self):
        self.assertFalse(self.store.sync())
        self.assertFalse(self.store.pull())

    def test_two_machines_share_a_store_through_git(self):
        self.git("init", "-q", "--bare", str(self.dir / "remote.git"))
        one = self.clone("one")
        one.append("a", {"type": "start"})
        # The first push sets the upstream branch, which sync() leaves to the person who made the clone
        self.git("-C", str(one.root), "add", "events")
        self.git("-C", str(one.root), "commit", "-qm", "seed")
        self.git("-C", str(one.root), "push", "-qu", "origin", "HEAD")
        two = self.clone("two")
        two.append("a", {"type": "archive", "actor": "parent"}, writer="parent")
        self.assertTrue(two.sync(retries=0))
        one.append("a", {"type": "report"})
        self.assertTrue(one.sync(retries=0))  # Both machines wrote, and the rebase finds no conflict
        self.assertTrue(two.pull())
        self.assertEqual(sorted(e["id"] for e in two.read("a")), ["a#1", "a#2", "a@parent#1"])

    def test_a_failing_push_is_retried_with_a_growing_delay(self):
        (self.store.root / ".git").mkdir(parents=True)
        failed = subprocess.CompletedProcess([], 1)
        with mock.patch.object(EventStore, "_git", return_value=failed), \
                mock.patch.object(store_module.time, "sleep") as sleep:
            self.assertFalse(self.store.sync(retries=3, backoff=1))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2, 4])


class HubTest(TmpCase):
    def test_a_slow_client_is_dropped(self):
        hub = Hub(self.store)
        slow: queue.Queue = queue.Queue(maxsize=1)
        hub.clients.add(slow)
        hub._broadcast("update", {})
        hub._broadcast("update", {})
        self.assertNotIn(slow, hub.clients)
        self.assertIsNone(slow.get_nowait())  # Tells the stream to close, so that the browser reconnects

    def test_the_client_cannot_choose_the_sequence_or_the_time(self):
        res = Hub(self.store).ingest({"session_id": "s", "fields": {
            "type": "start", "seq": 50, "ts": "2000-01-01T00:00:00Z", "session_id": "x"}})
        self.assertEqual((res["event"]["session_id"], res["event"]["seq"]), ("s", 1))
        self.assertGreater(res["event"]["ts"], "2026")

    def test_a_malformed_body_is_refused(self):
        hub = Hub(self.store)
        for body in ([], {}, {"session_id": "s"}, {"session_id": "s", "fields": []}, {"session_id": 1, "fields": {}}):
            with self.subTest(body), self.assertRaises(schema.SchemaError):
                hub.ingest(body)

    def test_publish_reports_changes_alone(self):
        hub = Hub(self.store)
        q, _ = hub.subscribe()
        self.assertFalse(hub.publish())
        self.assertTrue(q.empty())
        self.store.append("s", {"type": "start"})
        self.assertTrue(hub.publish())
        self.assertIn('"id":"s#1"', q.get_nowait())
        hub.publish(force=True)
        self.assertIn('"events":[]', q.get_nowait())
        hub.unsubscribe(q)
        self.assertEqual(hub.clients, set())

    def test_a_failing_sink_does_not_stop_the_hub(self):
        self.store.root.mkdir()
        (self.store.root / "collections.json").write_text(json.dumps(
            [{"name": "c", "sinks": [{"type": "jsonl", "path": "../x"}]}]))
        with redirect_stdout(StringIO()) as out:
            Hub(self.store)
        self.assertIn("sink write failed", out.getvalue())

    def test_the_loop_publishes_direct_writes_and_survives_a_failure(self):
        hub = Hub(self.store, watch_files=True, refresh_every=0, ping_every=0)
        q, _ = hub.subscribe()
        self.store.append("s", {"type": "start"})
        real, calls = hub.publish, []

        def publish(force=False):
            calls.append(force)
            if len(calls) == 1:
                raise OSError("transient")
            return real(force)

        with mock.patch.object(hub, "publish", publish), redirect_stdout(StringIO()) as out, \
                mock.patch.object(hub._stop, "wait", side_effect=[False, False, True]):
            hub.run()
        self.assertIn("periodic task failed: transient", out.getvalue())
        self.assertEqual(calls, [False, False, True])
        messages = [q.get_nowait() for _ in range(q.qsize())]
        self.assertIn(": ping\n\n", messages)
        self.assertTrue(any('"id":"s#1"' in m for m in messages))

    def test_the_loop_pulls_a_git_store(self):
        hub = Hub(self.store, pull_every=0.0001, refresh_every=999)
        with mock.patch.object(EventStore, "is_git", return_value=True), \
                mock.patch.object(EventStore, "pull") as pull, \
                mock.patch("session_hub.server.time.monotonic", side_effect=[0, 1]), \
                mock.patch.object(hub._stop, "wait", side_effect=[False, True]):
            hub.run()
        pull.assert_called_once_with()

    def test_stop_ends_every_stream(self):
        hub = Hub(self.store)
        q, _ = hub.subscribe()
        full: queue.Queue = queue.Queue(maxsize=1)
        full.put("x")
        hub.clients.add(full)
        hub.stop()
        self.assertIsNone(q.get_nowait())

    def test_a_public_address_needs_a_token(self):
        with self.assertRaisesRegex(SystemExit, "HUB_TOKEN"):
            make_server(self.store, host="0.0.0.0", port=0)


class HttpTest(TmpCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.hub = make_server(self.store, port=0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def request(self, method, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, res.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def test_unknown_paths(self):
        for method in ("GET", "POST", "DELETE"):
            self.assertEqual(self.request(method, "/nope")[0], 404)

    def test_body_errors(self):
        for body, want in ((b"", 400), (b"{", 400), (b"\xff", 400), (b"[]", 400), (b"x" * (64 * 1024 + 1), 413)):
            with self.subTest(body[:4]):
                self.assertEqual(self.request("POST", "/api/events", body)[0], want)

    def test_a_task_without_a_name_is_refused(self):
        code, text = self.request("POST", "/api/events", json.dumps(
            {"session_id": "s", "fields": {"type": "report", "tasks": [{"s": "done"}]}}).encode())
        self.assertEqual(code, 400)
        self.assertIn("name", text)
        self.assertEqual(self.store.read("s"), [])

    def test_pages_and_snapshot(self):
        self.assertEqual(self.request("GET", "/healthz"), (200, "ok"))
        self.assertIn("<html", self.request("GET", "/index.html")[1])
        self.store.append("s", {"type": "start"})
        self.hub.publish()
        self.assertEqual(json.loads(self.request("GET", "/api/snapshot")[1])["sessions"][0]["session_id"], "s")

    def test_delete_errors(self):
        self.assertEqual(self.request("DELETE", "/api/sessions/none")[0], 404)
        self.assertEqual(self.request("DELETE", "/api/sessions/a%2Fb")[0], 400)


class TranscriptTest(TmpCase):
    def test_usage_skips_what_it_cannot_read(self):
        path = self.dir / "t.jsonl"
        self.assertEqual(usage.usage_from_transcript(path)["turns"], 0)
        rows = [[1], {"message": "x"}, {"message": {"role": "user", "usage": {"input_tokens": 9}}},
                {"message": {"role": "assistant"}},
                {"uuid": "u", "message": {"role": "assistant", "usage": {
                    "input_tokens": 1, "output_tokens": None, "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 3}}}]
        path.write_text("not json\n" + "\n".join(map(json.dumps, rows)) + "\n")
        self.assertEqual(usage.usage_from_transcript(path),
                         {"input": 1, "output": 0, "cache_read": 2, "cache_write": 3, "turns": 1})

    def test_the_session_name_without_a_transcript(self):
        self.assertIsNone(session_name.from_transcript(None))
        self.assertIsNone(session_name.from_transcript(str(self.dir / "missing")))

    def test_desktop_default_root(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            os.environ.pop("HUB_DESKTOP_SESSIONS", None)
            with mock.patch.object(sys, "platform", "linux"):
                self.assertIsNone(desktop.default_root())
            with mock.patch.object(sys, "platform", "darwin"):
                self.assertEqual(desktop.default_root().parent.parent, self.dir / "Library" / "Application Support")

    def test_desktop_keeps_the_last_good_value(self):
        path = self.dir / "acc" / "org" / "local_1.json"
        path.parent.mkdir(parents=True)
        scan = desktop.DesktopSessions(self.dir).scan
        for text, want in (("{", {}), ("[]", {}), ('{"cliSessionId": 1, "isArchived": true}', {}),
                           ('{"cliSessionId": "s", "isArchived": true}', {"s": True}), ("{", {"s": True}),
                           ('{"cliSessionId": "s", "isArchived": false}', {"s": False})):
            path.write_text(text)
            self.assertEqual(scan(), want, text)
        path.unlink()
        self.assertEqual(scan(), {})


if __name__ == "__main__":
    unittest.main()
