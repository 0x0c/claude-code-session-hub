import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from session_hub import client, collections, core, hooks, local_state, schema, view
from session_hub.server import make_server
from session_hub.store import EventStore


class TmpMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.store = EventStore(self.dir / "store")

    def tearDown(self):
        self.tmp.cleanup()


class SchemaTest(TmpMixin, unittest.TestCase):
    def test_fold_ask_answer_cycle(self):
        sid = "s1"
        core.record(self.store, sid, {"type": "start", "title": "t", "tasks": [{"t": "a", "s": "doing"}]})
        res = core.record(self.store, sid, {"type": "ask", "attention": {
            "kind": "decision", "question": "q?", "options": ["x", "y"], "default": "x"}})
        self.assertEqual(res["status"]["state"], "needs_human")
        self.assertTrue(res["escalate"].startswith("[HUB/1] s1 needs_human q=2"))
        res = core.record(self.store, sid, {"type": "answer", "actor": "parent", "qid": 2, "value": "x"},
                          writer="parent")
        self.assertIsNone(res["status"]["attention"])
        self.assertEqual(res["status"]["state"], "working")
        self.assertIsNone(res["escalate"])  # 親自身の書き込みでは通知しない

    def test_validation_and_clipping(self):
        with self.assertRaises(schema.SchemaError):
            core.record(self.store, "s1", {"type": "nope"})
        with self.assertRaises(schema.SchemaError):
            core.record(self.store, "s1", {"type": "report", "state": "sleeping"})
        with self.assertRaises(schema.SchemaError):
            core.record(self.store, "../evil", {"type": "report"})
        ev = core.record(self.store, "s1", {"type": "report", "summary": "あ" * 300})["event"]
        self.assertEqual(len(ev["summary"]), schema.LIMITS["summary"])

    def test_task_updates_merge(self):
        core.record(self.store, "s1", {"type": "start", "task_updates": ["a=doing:S", "b=todo"]})
        st = core.record(self.store, "s1", {"type": "report", "task_updates": ["a=done", "c=todo:L", "b=-"]})["status"]
        self.assertEqual([(t["t"], t["s"], t["size"]) for t in st["tasks"]], [("a", "done", "S"), ("c", "todo", "L")])
        self.assertEqual(schema.task_progress(st["tasks"]), {"done": 1, "total": 2, "remaining": 8})

    def test_review_gate(self):
        core.record(self.store, "s1", {"type": "start", "tasks": [{"t": "a", "s": "doing"}]})
        res = core.record(self.store, "s1", {"type": "ready", "ready": {"self_review": True}})
        self.assertIsNone(res["escalate"])
        self.assertIn("PRなし", schema.ready_gate(res["status"]))
        core.record(self.store, "s1", {"type": "pr", "actor": "script",
                                       "pr": {"number": 3, "ci": "pass", "mergeable": True, "unresolved_threads": 0}})
        core.record(self.store, "s1", {"type": "report", "state": "working", "tasks": [{"t": "a", "s": "done"}]})
        res = core.record(self.store, "s1", {"type": "ready", "ready": {
            "self_review": True, "tests_added": True, "description": True}})
        self.assertEqual(schema.ready_gate(res["status"]), [])
        self.assertTrue(res["escalate"].startswith("[HUB/1] s1 review_ready PR#3"))

    def test_view_priority_and_timeline_diff(self):
        core.record(self.store, "a", {"type": "start", "title": "A"})
        core.record(self.store, "b", {"type": "fail", "last_error": "boom"})
        snap = view.snapshot(self.store.read_all())
        self.assertEqual([s["session_id"] for s in snap["sessions"]], ["b", "a"])
        self.assertEqual(view.attention_lines(snap), ["FL b boom"])
        start = next(e for e in snap["events"] if e["session_id"] == "a")
        self.assertEqual(start["diff"]["state"], {"from": "queued", "to": "planning"})


class CollectionsTest(TmpMixin, unittest.TestCase):
    def learn(self, sid, **f):
        return core.record(self.store, sid, {"type": "finding", "finding": f})

    def test_knowledge_aggregates_across_sessions(self):
        self.learn("a", kind="caveat", title="Redis 6.2  の SCAN", body="詳細", tags=["CI"], scope="tests/")
        self.learn("b", kind="caveat", title="redis 6.2 の scan", tags=["redis"], scope="search/")
        self.learn("b", kind="decision", title="上限 120")
        snap = view.snapshot(self.store.read_all())
        items = snap["collections"]["knowledge"]["items"]
        self.assertEqual(len(items), 2)
        cav = next(i for i in items if i["kind"] == "caveat")
        self.assertEqual((cav["count"], cav["reporters"], cav["tags"]), (2, ["a", "b"], ["ci", "redis"]))
        self.assertEqual((cav["body"], cav["scopes"]), ("詳細", ["search/", "tests/"]))
        self.learn("a", kind="caveat", title="Redis 6.2 の SCAN", status="obsolete")
        snap = view.snapshot(self.store.read_all())
        self.assertEqual(snap["collections"]["knowledge"]["active"], 1)
        self.assertEqual(view.knowledge_lines(snap), ["[decision] 上限 120"])

    def test_user_defined_collection_and_sink(self):
        (self.store.root).mkdir(parents=True, exist_ok=True)
        (self.store.root / "collections.json").write_text(json.dumps([
            {"name": "knowledge", "sinks": [{"type": "markdown", "path": "out/K.md"}]},
            {"name": "pr", "label": "PR", "match": {"type": ["pr"]},
             "reduce": {"type": "latest", "payload": None, "key": ["session_id"]}, "view": {"type": "table"}},
        ]))
        defs = collections.load_definitions(self.store.root)
        core.record(self.store, "a", {"type": "pr", "actor": "script", "pr": {"number": 1}})
        core.record(self.store, "a", {"type": "pr", "actor": "script", "pr": {"ci": "pass"}})
        self.learn("a", kind="howto", title="make up で起動")
        snap = view.snapshot(self.store.read_all(), defs=defs)
        self.assertEqual(len(snap["collections"]["pr"]["items"]), 1)
        written = collections.write_sinks(defs, snap["collections"], self.store.root)
        self.assertIn("make up で起動", (self.store.root / "out/K.md").read_text())
        self.assertEqual(len(written), 1)
        self.assertEqual(collections.write_sinks(defs, snap["collections"], self.store.root), [])  # 変化なし

    def test_invalid_definitions(self):
        with self.assertRaises(collections.CollectionError):
            collections._validate({"name": "x", "reduce": {"type": "zzz"}})
        with self.assertRaises(collections.CollectionError):
            defs = [collections._validate({"name": "x", "sinks": [{"type": "jsonl", "path": "../../evil"}]})]
            collections.write_sinks(defs, {"x": {"items": []}}, self.store.root)
        with self.assertRaises(schema.SchemaError):
            self.learn("a", kind="rumor", title="x")


class StoreTest(TmpMixin, unittest.TestCase):
    def test_per_writer_files_and_ordering(self):
        self.store.append("s1", {"type": "report", "summary": "1"})
        self.store.append("s1", {"type": "command", "actor": "parent", "note": "x"}, writer="parent")
        self.store.append("s1", {"type": "report", "summary": "2"})
        names = sorted(p.name for p in (self.store.root / "events").iterdir())
        self.assertEqual(names, ["s1.jsonl", "s1@parent.jsonl"])
        self.assertEqual([e["id"] for e in self.store.read("s1")], ["s1#1", "s1@parent#1", "s1#2"])
        self.assertEqual(self.store.session_ids(), ["s1"])

    def test_corrupt_and_duplicate_lines_are_skipped(self):
        self.store.append("s1", {"type": "report", "summary": "ok"})
        path = self.store.root / "events" / "s1.jsonl"
        line = path.read_text().strip()
        path.write_text(line + "\n{broken\n" + line + "\n")
        self.assertEqual(len(self.store.read("s1")), 1)


class ServerTest(TmpMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.hub = make_server(self.store, port=0, token="tok")
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.hub.stop()
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def test_push_is_broadcast_to_stream(self):
        req = urllib.request.Request(self.url + "/api/stream", headers={"Authorization": "Bearer tok"})
        stream = urllib.request.urlopen(req, timeout=5)

        def read_event():
            name, data = None, None
            while True:
                line = stream.readline().decode().rstrip("\n")
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                elif line == "" and name:
                    return name, data

        self.assertEqual(read_event()[0], "snapshot")
        res = client.post(self.url, {"session_id": "c1", "fields": {"type": "start", "title": "子"}}, token="tok")
        self.assertEqual(res["status"]["state"], "planning")
        name, data = read_event()
        self.assertEqual(name, "update")
        self.assertEqual([e["id"] for e in data["events"]], ["c1#1"])
        self.assertEqual(data["sessions"][0]["title"], "子")
        stream.close()

    def test_auth_and_validation(self):
        with self.assertRaises(ValueError):  # 4xx は ValueError（再送しない）
            client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="wrong")
        with self.assertRaises(ValueError):
            client.post(self.url, {"session_id": "c1", "fields": {"type": "bogus"}}, token="tok")
        with self.assertRaises(client.PushError):
            client.get_snapshot(self.url)  # トークンなしの読み取りも拒否
        self.assertEqual(client.get_snapshot(self.url, "tok")["sessions"], [])

    def test_outbox_flush(self):
        env = {"HUB_OUTBOX": str(self.dir / "outbox.jsonl")}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(client.push("http://127.0.0.1:9", {"session_id": "c1", "fields": {"type": "start"}}))
            self.assertTrue(Path(env["HUB_OUTBOX"]).exists())
            client.push(self.url, {"session_id": "c1", "fields": {"type": "report", "summary": "2"}}, token="tok")
            self.assertFalse(Path(env["HUB_OUTBOX"]).exists())
        self.assertEqual([e["type"] for e in self.store.read("c1")], ["start", "report"])


class HooksTest(TmpMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, {
            "HUB_STORE": str(self.store.root), "HUB_SESSION_ID": "kid", "HUB_STATE_DIR": str(self.dir / "state"),
            "HOME": str(self.dir / "home")})
        self.env.start()
        os.environ.pop("HUB_URL", None)

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def run_hook(self, name, payload):
        buf = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), redirect_stdout(buf):
            hooks.run(name)
        return buf.getvalue().strip()

    def test_stop_guard(self):
        out = json.loads(self.run_hook("stop", {}))
        self.assertEqual(out["decision"], "block")  # 未登録
        self.assertEqual(self.run_hook("stop", {"stop_hook_active": True}), "")
        res = core.record(self.store, "kid", {"type": "start", "title": "x"})
        local_state.note("kid", {"type": "start"}, res)
        self.assertIn("作業中", json.loads(self.run_hook("stop", {}))["reason"])
        res = core.record(self.store, "kid", {"type": "done"})
        local_state.note("kid", {"type": "done"}, res)
        self.assertEqual(self.run_hook("stop", {}), "")

    def test_stop_records_usage(self):
        t = self.dir / "t.jsonl"
        msg = lambda i, n: json.dumps({"message": {"id": i, "role": "assistant", "usage": {"input_tokens": n, "output_tokens": 1}}})  # noqa: E731
        t.write_text("\n".join([msg("a", 10), msg("a", 10), msg("b", 5)]) + "\n")
        self.run_hook("stop", {"transcript_path": str(t), "stop_hook_active": True})
        st = schema.fold(self.store.read("kid"))
        self.assertEqual((st["usage"]["input"], st["usage"]["output"]), (15, 2))

    def test_todo_sync(self):
        self.run_hook("todo", {"tool_name": "TodoWrite", "tool_input": {"todos": [
            {"content": "a", "status": "completed", "activeForm": "A"},
            {"content": "b", "status": "in_progress", "activeForm": "B をしている"}]}})
        st = schema.fold(self.store.read("kid"))
        self.assertEqual([(t["t"], t["s"]) for t in st["tasks"]], [("a", "done"), ("b", "doing")])
        self.assertEqual((st["summary"], st["state"]), ("B をしている", "working"))
        self.run_hook("todo", {"tool_name": "TaskCreate", "tool_input": {"subject": "c"},
                               "tool_response": {"task": {"id": "9"}}})
        self.run_hook("todo", {"tool_name": "TaskUpdate", "tool_input": {"taskId": "9", "status": "completed"}})
        st = schema.fold(self.store.read("kid"))
        self.assertIn(("c", "done"), [(t["t"], t["s"]) for t in st["tasks"]])

    def test_disabled_without_config(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HUB_STORE")
            self.assertEqual(self.run_hook("stop", {}), "")
            self.assertEqual(self.run_hook("todo", {"tool_name": "TodoWrite", "tool_input": {"todos": []}}), "")


if __name__ == "__main__":
    unittest.main()
