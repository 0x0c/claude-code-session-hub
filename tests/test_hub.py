import http.client
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from session_hub import cli, client, collections, core, desktop, hooks, local_state, project, schema, view
from session_hub.server import make_server
from session_hub.deliver import deliver
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
        self.assertIsNone(res["escalate"])  # The parent's own write does not notify

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
        self.assertIn("no PR", schema.ready_gate(res["status"]))
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


class ArchiveTest(TmpMixin, unittest.TestCase):
    def status(self):
        return view.session_view(self.store.read("s"))[0]

    def test_archive_keeps_the_state_and_silences_attention(self):
        self.store.append("s", {"type": "ask", "attention": {"kind": "decision", "question": "?"}})
        before = self.status()
        self.assertTrue(before["needs_action"])
        self.store.append("s", {"type": "archive", "actor": "script"}, writer="desktop")
        st, tl = view.session_view(self.store.read("s"))
        self.assertEqual(st["state"], "needs_human")
        self.assertEqual(st["heartbeat"], before["heartbeat"])
        self.assertFalse(st["needs_action"])
        self.assertIn("archived", tl[-1]["diff"])
        self.assertEqual(view.attention_lines({"sessions": [st]}), [])
        self.store.append("s", {"type": "unarchive", "actor": "script"}, writer="desktop")
        after = self.status()
        self.assertTrue(after["needs_action"])
        self.assertEqual(after["attention"], before["attention"])

    def test_archived_session_does_not_wake_the_parent(self):
        ask = {"type": "ask", "attention": {"kind": "decision", "question": "?"}}
        for writer, escalates in (("desktop", False), ("parent", True)):
            self.store.delete_session("s")
            self.store.append("s", {"type": "start", "state": "working"})
            self.store.append("s", {"type": "archive"}, writer=writer)
            res = core.record(self.store, "s", ask)
            self.assertEqual(bool(res["escalate"]), escalates)  # The ask reopens a manual archive
            self.assertEqual("archived" in res["message"], not escalates)
            self.assertEqual(self.status()["needs_action"], escalates)

    def test_archived_session_is_never_stale(self):
        self.store.append("s", {"type": "start", "state": "working"})
        self.store.append("s", {"type": "archive"}, writer="parent")
        st, _ = view.session_view(self.store.read("s"), stale_minutes=0)
        self.assertFalse(st["stale"])

    def test_archive_events_alone_make_no_session(self):
        self.store.append("s", {"type": "archive", "actor": "parent"}, writer="parent")
        self.assertEqual(self.status()["archived"]["by"], "parent")
        self.assertEqual(view.snapshot(self.store.read_all())["sessions"], [])

    def test_report_reopens_a_manual_archive_alone(self):
        for writer, reopened in (("parent", True), ("desktop", False)):
            self.store.delete_session("s")
            self.store.append("s", {"type": "start"})
            self.store.append("s", {"type": "archive", "actor": "parent"}, writer=writer)
            self.store.append("s", {"type": "heartbeat", "actor": "hook"})
            self.store.append("s", {"type": "report", "actor": "hook", "summary": "todo"})
            self.assertTrue(self.status()["archived"])
            self.store.append("s", {"type": "report", "state": "working"})
            self.assertEqual(self.status()["archived"] is None, reopened)
            self.store.append("s", {"type": "unarchive"}, writer=writer)
            self.store.append("s", {"type": "archive"}, writer=writer)
            self.store.append("s", {"type": "pr", "actor": "script", "pr": {"number": 1}})
            self.assertEqual(self.status()["archived"] is None, reopened)


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
        self.assertEqual(collections.write_sinks(defs, snap["collections"], self.store.root), [])  # No change

    def test_invalid_definitions(self):
        with self.assertRaises(collections.CollectionError):
            collections._validate({"name": "x", "reduce": {"type": "zzz"}})
        with self.assertRaises(collections.CollectionError):
            defs = [collections._validate({"name": "x", "sinks": [{"type": "jsonl", "path": "../../evil"}]})]
            collections.write_sinks(defs, {"x": {"items": []}}, self.store.root)
        with self.assertRaises(schema.SchemaError):
            self.learn("a", kind="rumor", title="x")


class LocalizationTest(TmpMixin, unittest.TestCase):
    def test_gate_codes_back_the_cli_messages(self):
        core.record(self.store, "s1", {"type": "start", "tasks": [{"t": "a", "s": "doing"}]})
        st = core.record(self.store, "s1", {"type": "pr", "actor": "script", "pr": {"number": 3}})["status"]
        codes = schema.ready_gate_codes(st)
        self.assertEqual([c["code"] for c in codes],
                         ["ci", "self_review", "tests_added", "description", "tasks"])
        self.assertEqual(codes[0]["value"], "unknown")
        self.assertEqual(schema.ready_gate(st)[0], "CI: unknown")
        view_st = view.snapshot(self.store.read_all())["sessions"][0]
        self.assertEqual(view_st["gate_codes"], codes)

    def test_localized_display_strings(self):
        label = {"en": "Knowledge", "ja": "ナレッジ"}
        self.assertEqual(collections.localized(label, "en"), "Knowledge")
        self.assertEqual(collections.localized(label), "Knowledge")  # the CLI default is English
        self.assertEqual(collections.localized(label, "ja"), "ナレッジ")
        self.assertEqual(collections.localized({"en": "Only English"}, "ja"), "Only English")
        self.assertEqual(collections.localized("plain", "en"), "plain")

    def test_markdown_sink_language(self):
        (self.store.root).mkdir(parents=True, exist_ok=True)
        (self.store.root / "collections.json").write_text(json.dumps([
            {"name": "knowledge", "sinks": [{"type": "markdown", "path": "K.en.md", "lang": "en"},
                                            {"type": "markdown", "path": "K.ja.md", "lang": "ja"}]}]))
        defs = collections.load_definitions(self.store.root)
        core.record(self.store, "a", {"type": "finding", "finding": {"kind": "caveat", "title": "x"}})
        snap = view.snapshot(self.store.read_all(), defs=defs)
        collections.write_sinks(defs, snap["collections"], self.store.root)
        self.assertTrue((self.store.root / "K.en.md").read_text().startswith("# Knowledge\n"))
        self.assertIn("## Caveats", (self.store.root / "K.en.md").read_text())
        self.assertTrue((self.store.root / "K.ja.md").read_text().startswith("# ナレッジ\n"))


class ProjectTest(TmpMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        env = {"HUB_STATE_DIR": str(self.dir / "state"), "HUB_STORE": str(self.dir / "store"),
               "HUB_SESSION_ID": "s1", "HOME": str(self.dir), "GIT_CEILING_DIRECTORIES": str(self.dir.resolve())}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        for k in ("HUB_URL", "HUB_AUTOSTART", "CLAUDE_PROJECT_DIR", "CLAUDE_CODE_REMOTE_SESSION_ID"):
            os.environ.pop(k, None)

    def git(self, *args, cwd):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                       cwd=cwd, check=True, capture_output=True)

    def repo(self, name="app"):
        path = self.dir / name
        path.mkdir()
        self.git("init", cwd=path)
        return path

    def test_name_from_remote(self):
        for url, want in {
            "https://github.com/acme/app.git": "acme/app",
            "https://user:secret@github.com/acme/app": "acme/app",
            "git@github.com:acme/app.git": "acme/app",
            "ssh://git@host:2222/acme/app.git/": "acme/app",
            "https://gitlab.com/acme/team/app.git": "acme/team/app",
            "/srv/git/app.git": "app", "file:///srv/git/app.git": "app", "../app": "app",
            "https://github.com/": None, "https://[broken/app": None,
        }.items():
            self.assertEqual(project.name_from_remote(url), want, url)

    def test_detect_remote_worktree_and_plain_folder(self):
        app = self.repo()
        self.git("commit", "--allow-empty", "-m", "x", cwd=app)
        self.git("worktree", "add", str(self.dir / "wt"), cwd=app)
        (app / "sub").mkdir()
        for path in (app, app / "sub", self.dir / "wt"):
            self.assertEqual(project.detect(str(path)), "app")
        self.git("remote", "add", "origin", "git@github.com:acme/app.git", cwd=app)
        self.assertEqual(project.detect(str(self.dir / "wt")), "acme/app")
        (self.dir / "notes").mkdir()
        self.assertEqual(project.detect(str(self.dir / "notes")), "notes")
        with mock.patch("session_hub.project.subprocess.run", side_effect=OSError):
            self.assertEqual(project.detect(str(app)), "app")

    def start(self, *args):
        from session_hub import cli
        with redirect_stdout(io.StringIO()):
            cli.main(["--no-sync", *args])

    def test_start_detects_and_an_explicit_project_wins(self):
        with mock.patch.object(project, "detect", return_value="acme/app"):
            self.start("start", "--title", "t")
            self.assertEqual(schema.fold(self.store.read("s1"))["repo"], "acme/app")
            self.start("start", "--repo", "other")
            hooks.stop({})
            self.assertEqual(schema.fold(self.store.read("s1"))["repo"], "other")
            self.start("--session", "s2", "start", "--title", "registered by the parent")
            self.assertIsNone(schema.fold(self.store.read("s2"))["repo"])

    def test_stop_hook_fills_the_project_of_a_running_session(self):
        core.record(self.store, "s1", {"type": "start", "title": "before the upgrade"})
        with mock.patch.object(project, "detect", return_value="acme/app"):
            hooks.stop({})
        self.assertEqual(schema.fold(self.store.read("s1"))["repo"], "acme/app")

    def test_heartbeat_keeps_a_project_the_local_state_never_saw(self):
        core.record(self.store, "s1", {"type": "start", "repo": "payments"})
        with mock.patch.object(project, "detect", return_value="acme/app"):
            hooks.stop({})
        events = self.store.read("s1")
        self.assertEqual(schema.fold(events)["repo"], "payments")
        self.assertNotIn("repo", events[-1])  # An older hub would apply `repo` unconditionally

    def test_long_project_is_clipped(self):
        st = core.record(self.store, "s1", {"type": "start", "repo": "x" * 200})["status"]
        self.assertEqual(len(st["repo"]), schema.LIMITS["repo"])

    def test_session_start_remembers_the_project_folder(self):
        with mock.patch.object(project, "detect", return_value="acme/app"), \
                mock.patch.object(hooks, "install_shim", return_value=None):
            hooks.session_start({})
        with mock.patch.object(project, "detect", return_value="elsewhere"):
            self.start("start", "--title", "t")
        self.assertEqual(schema.fold(self.store.read("s1"))["repo"], "acme/app")


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


    def test_delete_session_removes_every_writer_file(self):
        self.store.append("s1", {"type": "report", "summary": "1"})
        self.store.append("s1", {"type": "command", "actor": "parent", "note": "x"}, writer="parent")
        self.store.append("s10", {"type": "report", "summary": "other"})
        self.assertEqual(self.store.delete_session("s1"), 2)
        self.assertEqual(self.store.session_ids(), ["s10"])  # A session that shares the prefix stays
        self.assertEqual(self.store.read("s1"), [])
        self.assertEqual(self.store.delete_session("s1"), 0)
        with self.assertRaises(schema.SchemaError):
            self.store.delete_session("../evil")

    def test_append_after_delete_reopens_the_file(self):
        # A writer that opened the file before the deletion must not lose its event
        self.store.append("s1", {"type": "report", "summary": "old"})
        path = self.store.root / "events" / "s1.jsonl"
        real_open = open
        opened = []

        def racing_open(file, *args, **kwargs):
            f = real_open(file, *args, **kwargs)
            if Path(file) == path and not opened:
                opened.append(True)
                self.store.delete_session("s1")  # Deleted between open() and the lock
            return f

        with mock.patch("builtins.open", racing_open):
            ev = self.store.append("s1", {"type": "report", "summary": "new"})
        self.assertEqual(ev["seq"], 1)
        self.assertEqual([e["summary"] for e in self.store.read("s1")], ["new"])


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

    def test_stop_requires_the_token(self):
        with self.assertRaises(ValueError):
            client.stop_server(self.url, "wrong")
        self.assertTrue(client.healthy(self.url))

    def test_stop_refuses_a_remote_client(self):
        handler = self.httpd.RequestHandlerClass
        with mock.patch.object(handler, "setup", autospec=True, side_effect=self._remote_setup(handler.setup)):
            with self.assertRaisesRegex(ValueError, "403"):
                client.stop_server(self.url, "tok")
        self.assertTrue(client.healthy(self.url))

    @staticmethod
    def _remote_setup(real):
        def setup(handler):
            handler.client_address = ("192.0.2.1", 1)
            real(handler)
        return setup

    def test_stop_refuses_a_browser_page(self):
        for origin in ("http://evil.example:8765", "null"):
            req = urllib.request.Request(self.url + "/api/server", method="DELETE",
                                         headers={"Authorization": "Bearer tok", "Origin": origin})
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(cm.exception.code, 403)
            cm.exception.close()
        self.assertTrue(client.healthy(self.url))

    def test_stop_reports_an_old_hub(self):
        err = urllib.error.HTTPError(self.url, 404, "not found", {}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertFalse(client.stop_server(self.url, "tok"))
        with mock.patch.object(client, "stop_server", return_value=False), \
                mock.patch.dict(os.environ, {"HUB_URL": self.url}), \
                self.assertRaisesRegex(SystemExit, "older version"):
            cli.main(["stop"])

    def test_stop_reaches_a_hub_that_answers_slowly(self):
        answers = iter([False, True, False, False, False])  # One timeout, then alive, then gone
        out = io.StringIO()
        with mock.patch.object(client, "healthy", side_effect=lambda url: next(answers)), \
                mock.patch.object(client, "stop_server", return_value=True) as stop, \
                mock.patch.dict(os.environ, {"HUB_URL": self.url}), redirect_stdout(out):
            cli.main(["stop"])
        stop.assert_called_once()
        self.assertEqual(list(answers), [])
        self.assertIn("stopped the hub", out.getvalue())

    def test_stop_timeout_is_not_reported_as_stopped(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")), \
                mock.patch.dict(os.environ, {"HUB_URL": self.url}), \
                self.assertRaisesRegex(SystemExit, "unreachable"):
            cli.main(["stop"])

    def test_stop_refuses_a_remote_hub(self):
        with mock.patch.dict(os.environ, {"HUB_URL": "https://hub.example"}), \
                self.assertRaisesRegex(SystemExit, "not on this machine"):
            cli.main(["stop"])

    def test_stop_command_ends_the_server_process(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        env.update(HUB_STORE=str(self.dir / "other"), HUB_TOKEN="tok")
        proc = subprocess.Popen([sys.executable, "-m", "session_hub", "serve", "--port", "0"], env=env,
                                cwd=Path(__file__).resolve().parent.parent, stdout=subprocess.PIPE, text=True)
        try:
            url = proc.stdout.readline().split()[2].rstrip("/")
            # An open dashboard must not keep the process alive
            req = urllib.request.Request(url + "/api/stream", headers={"Authorization": "Bearer tok"})
            with urllib.request.urlopen(req, timeout=5) as stream, \
                    mock.patch.dict(os.environ, {"HUB_URL": url, "HUB_TOKEN": "tok"}):
                stream.readline()
                out = io.StringIO()
                with redirect_stdout(out):
                    cli.main(["stop"])
                    self.assertEqual(proc.wait(timeout=10), 0)
                    cli.main(["stop"])  # Stopping a stopped hub is not an error
            self.assertIn("stopped the hub", out.getvalue())
            self.assertIn("no hub is running", out.getvalue())
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            proc.stdout.close()

    def test_delete_session_is_broadcast_to_stream(self):
        client.post(self.url, {"session_id": "c1", "fields": {"type": "start", "title": "a"}}, token="tok")
        client.post(self.url, {"session_id": "c1", "writer": "parent",
                               "fields": {"type": "command", "actor": "parent", "note": "go"}}, token="tok")
        client.post(self.url, {"session_id": "c2", "fields": {"type": "start", "title": "b"}}, token="tok")
        req = urllib.request.Request(self.url + "/api/stream", headers={"Authorization": "Bearer tok"})
        stream = urllib.request.urlopen(req, timeout=5)

        def read_event():
            name = None
            while True:
                line = stream.readline().decode().rstrip("\n")
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                elif line == "" and name:
                    return name, data

        self.assertEqual(read_event()[0], "snapshot")
        with self.assertRaises(ValueError):
            client.delete_session(self.url, "c1", token="wrong")
        self.assertEqual(client.delete_session(self.url, "c1", token="tok"), {"session_id": "c1", "deleted": 2})
        name, data = read_event()
        self.assertEqual(name, "update")
        self.assertEqual(sorted(data["removed"]), ["c1#1", "c1@parent#1"])
        self.assertEqual([x["session_id"] for x in data["sessions"]], ["c2"])
        stream.close()
        self.assertEqual(self.store.session_ids(), ["c2"])
        self.assertIsNone(client.delete_session(self.url, "c1", token="tok"))  # 404
        with self.assertRaises(ValueError):
            client.delete_session(self.url, "bad@id", token="tok")  # 400

    def test_cli_delete_routes(self):
        from session_hub import cli
        client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="tok")
        self.store.append("c2", {"type": "start"})
        env = {"HUB_URL": self.url, "HUB_TOKEN": "tok", "HUB_STORE": str(self.store.root)}
        with mock.patch.dict(os.environ, env):
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["delete", "c1"])  # Through the hub
            self.assertEqual(out.getvalue().strip(), "deleted c1 (1 events)")
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                cli.main(["delete", "c1"])
        with mock.patch.dict(os.environ, {**env, "HUB_URL": "http://127.0.0.1:9"}):
            out = io.StringIO()
            with redirect_stdout(out), mock.patch("sys.stderr", io.StringIO()):
                cli.main(["delete", "c2"])  # The hub is down: delete from the shared store
            self.assertEqual(out.getvalue().strip(), "deleted c2 (1 events)")
        self.assertEqual(self.store.session_ids(), [])

    def desktop_file(self, sid, archived, name="a"):
        d = self.dir / "desktop" / "acct" / "org"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"local_{name}.json"
        path.write_text(json.dumps({"cliSessionId": sid, "isArchived": archived}))
        return path

    def test_desktop_archive_is_mirrored(self):
        self.hub.desktop = desktop.DesktopSessions(self.dir / "desktop")
        self.assertEqual(self.hub.sync_desktop(), 0)  # The directory does not exist
        client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="tok")
        self.desktop_file("c1", False)
        self.desktop_file("unknown", True, "b")
        self.assertEqual(self.hub.sync_desktop(), 0)
        path = self.desktop_file("c1", True)
        q, _ = self.hub.subscribe()
        self.assertEqual(self.hub.sync_desktop(), 1)
        self.assertIn('"id":"c1@desktop#1"', q.get(timeout=1))
        self.assertEqual(self.hub.snap["sessions"][0]["archived"]["by"], "desktop")
        self.assertEqual(self.hub.sync_desktop(), 0)
        # A late report does not fight the app, and neither does a broken or vanished file
        client.post(self.url, {"session_id": "c1", "fields": {"type": "done"}}, token="tok")
        path.write_text("{")
        self.assertEqual(self.hub.sync_desktop(), 0)
        path.unlink()
        self.assertEqual(self.hub.sync_desktop(), 0)
        self.desktop_file("c1", False)
        self.assertEqual(self.hub.sync_desktop(), 1)
        self.assertIsNone(self.hub.snap["sessions"][0]["archived"])
        self.assertEqual(self.store.session_ids(), ["c1"])

    def test_desktop_leaves_manual_archives_and_deleted_sessions(self):
        self.hub.desktop = desktop.DesktopSessions(self.dir / "desktop")
        self.desktop_file("c1", False)
        client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="tok")
        client.post(self.url, {"session_id": "c1", "writer": "parent",
                               "fields": {"type": "archive", "actor": "parent"}}, token="tok")
        self.assertEqual(self.hub.sync_desktop(), 0)
        client.post(self.url, {"session_id": "c1", "fields": {"type": "report", "state": "working"}}, token="tok")
        self.desktop_file("c1", True)
        self.store.delete_session("c1")  # Behind the hub's back: the event must not bring it back
        self.assertEqual(self.hub.sync_desktop(), 0)
        self.assertEqual(self.store.session_ids(), [])

    def test_desktop_session_shared_by_two_app_sessions(self):
        self.desktop_file("c1", True, "a")
        self.desktop_file("c1", False, "b")
        d = desktop.DesktopSessions(self.dir / "desktop")
        self.assertEqual(d.scan(), {"c1": False})
        self.desktop_file("c1", True, "b")
        self.assertEqual(d.scan(), {"c1": True})

    def test_run_loop_survives_a_failing_desktop_scan(self):
        self.hub.desktop = desktop.DesktopSessions(self.dir)
        self.hub.desktop_every = 0.01
        calls = []

        def scan():
            calls.append(1)
            if len(calls) == 3:
                self.hub._stop.set()
            raise RuntimeError("boom")

        with mock.patch.object(self.hub.desktop, "scan", scan), redirect_stdout(io.StringIO()):
            t = threading.Thread(target=self.hub.run)
            t.start()
            t.join(5)
        self.assertEqual(len(calls), 3)

    def test_cli_archive(self):
        from session_hub import cli
        client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="tok")
        env = {"HUB_URL": self.url, "HUB_TOKEN": "tok", "HUB_STORE": str(self.store.root)}
        with mock.patch.dict(os.environ, env):
            with redirect_stdout(io.StringIO()):
                cli.main(["archive", "c1"])
            self.assertTrue(self.hub.snap["sessions"][0]["archived"])
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["status"])
            self.assertTrue(out.getvalue().startswith("AR c1"))
            with self.assertRaises(SystemExit):
                cli.main(["archive", "nope"])
        with mock.patch.dict(os.environ, {**env, "HUB_URL": "http://127.0.0.1:9"}):
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                cli.main(["unarchive", "c1"])  # The hub is down: write to the shared store
        self.assertIsNone(schema.fold(self.store.read("c1"))["archived"])
        self.assertEqual(self.store.session_ids(), ["c1"])

    def test_desktop_root_setting(self):
        for value, want in (("", None), ("0", None), ("/x", Path("/x"))):
            with mock.patch.dict(os.environ, {"HUB_DESKTOP_SESSIONS": value}):
                self.assertEqual(desktop.default_root(), want)

    def test_auth_and_validation(self):
        with self.assertRaises(ValueError):  # A 4xx raises ValueError (no retry)
            client.post(self.url, {"session_id": "c1", "fields": {"type": "start"}}, token="wrong")
        with self.assertRaises(ValueError):
            client.post(self.url, {"session_id": "c1", "fields": {"type": "bogus"}}, token="tok")
        with self.assertRaises(client.PushError):
            client.get_snapshot(self.url)  # A read without a token is rejected too
        self.assertEqual(client.get_snapshot(self.url, "tok")["sessions"], [])

    def test_local_fallback_writes_shared_store_when_server_down(self):
        from session_hub.deliver import deliver
        env = {"HUB_URL": "http://127.0.0.1:9", "HUB_STORE": str(self.store.root),
               "HUB_OUTBOX": str(self.dir / "outbox.jsonl"), "HUB_STATE_DIR": str(self.dir / "st")}
        with mock.patch.dict(os.environ, env):
            res, mode = deliver("c9", {"type": "start", "title": "down"})
            self.assertEqual((mode, res["status"]["state"]), ("store", "planning"))
            self.assertFalse(Path(env["HUB_OUTBOX"]).exists())
        # The server rereads the store on the next update, so messages sent while it was down appear too
        client.post(self.url, {"session_id": "c8", "fields": {"type": "start"}}, token="tok")
        self.assertIn("c9", [s["session_id"] for s in client.get_snapshot(self.url, "tok")["sessions"]])

    def test_outbox_flush(self):
        env = {"HUB_OUTBOX": str(self.dir / "outbox.jsonl")}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(client.push("http://127.0.0.1:9", {"session_id": "c1", "fields": {"type": "start"}}))
            self.assertTrue(Path(env["HUB_OUTBOX"]).exists())
            client.push(self.url, {"session_id": "c1", "fields": {"type": "report", "summary": "2"}}, token="tok")
            self.assertFalse(Path(env["HUB_OUTBOX"]).exists())
        self.assertEqual([e["type"] for e in self.store.read("c1")], ["start", "report"])


class HostCheckTest(TmpMixin, unittest.TestCase):
    """A page that rebinds its name to 127.0.0.1 sends that name in Host."""

    HOSTILE = ("evil.example:8765", "127.0.0.1.evil.example", "localhost.evil.example", "192.0.2.1", "[", "")

    def serve(self, token=None):
        httpd, hub = make_server(self.store, port=0, token=token)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.addCleanup(hub.stop)
        return httpd.server_address[1]

    def request(self, port, host, method="GET", path="/api/snapshot", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
            res = conn.getresponse()
            res.read()
            return res.status
        finally:
            conn.close()

    def test_foreign_host_is_refused_on_every_endpoint(self):
        core.record(self.store, "c1", {"type": "start", "title": "a"})
        port = self.serve()
        body = json.dumps({"session_id": "c2", "fields": {"type": "start", "title": "b"}})
        for host in self.HOSTILE:
            for method, path, data in (("GET", "/", None), ("GET", "/healthz", None), ("GET", "/api/snapshot", None),
                                       ("GET", "/api/stream", None), ("POST", "/api/events", body),
                                       ("DELETE", "/api/sessions/c1", None)):
                with self.subTest(host=host, method=method, path=path):
                    self.assertEqual(self.request(port, host, method, path, data), 403)
        self.assertEqual(list(self.store.read_all()), ["c1"])

    def test_a_refused_push_is_kept_in_the_outbox(self):
        err = urllib.error.HTTPError("http://hub.example", 403, "Forbidden", {}, io.BytesIO(b"{}"))
        outbox = self.dir / "outbox.jsonl"
        queued = {"session_id": "c1", "fields": {"type": "start", "title": "old"}}
        with mock.patch.dict(os.environ, {"HUB_OUTBOX": str(outbox)}), \
                mock.patch("urllib.request.urlopen", side_effect=err):
            client.spool(queued)
            self.assertIsNone(client.push("http://hub.example", {**queued, "session_id": "c2"}))
        kept = [json.loads(line)["session_id"] for line in outbox.read_text().splitlines()]
        self.assertEqual(kept, ["c1", "c2"])

    def test_local_hosts_are_served(self):
        port = self.serve()
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}", f"[::1]:{port}", "localhost"):
            with self.subTest(host=host):
                self.assertEqual(self.request(port, host), 200)

    def test_refusal_drops_the_unread_body(self):
        port = self.serve()
        smuggled = "GET /api/snapshot HTTP/1.1\r\nHost: localhost\r\n\r\n"
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(f"POST /api/events HTTP/1.1\r\nHost: evil.example\r\n"
                         f"Content-Length: {len(smuggled)}\r\n\r\n{smuggled}".encode())
            data = b""
            try:
                while chunk := sock.recv(4096):
                    data += chunk
            except ConnectionResetError:
                pass
        self.assertEqual(data.count(b"HTTP/1.1 "), 1)

    def test_a_token_admits_any_host(self):
        port = self.serve(token="tok")
        self.assertEqual(self.request(port, "hub.example", headers={"Authorization": "Bearer tok"}), 200)
        self.assertEqual(self.request(port, "hub.example"), 401)


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
        self.assertEqual(out["decision"], "block")  # Not registered
        self.assertEqual(self.run_hook("stop", {"stop_hook_active": True}), "")
        res = core.record(self.store, "kid", {"type": "start", "title": "x"})
        local_state.note("kid", {"type": "start"}, res)
        self.assertIn("still shows this session as working", json.loads(self.run_hook("stop", {}))["reason"])
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

    def test_session_name_becomes_the_title(self):
        t = self.dir / "t.jsonl"
        rec = lambda kind, field, name: json.dumps({"type": kind, field: name}, ensure_ascii=False) + "\n"  # noqa: E731
        start = {"type": "start", "title": "reported"}
        title = lambda: schema.fold(self.store.read("kid"))["title"]  # noqa: E731

        self.run_hook("session-start", {"transcript_path": str(t)})  # The file does not exist yet
        deliver("kid", start)
        self.assertEqual(title(), "reported")
        t.write_text("not json custom-title\n" + rec("ai-title", "aiTitle", "generated"), encoding="utf-8")
        deliver("kid", {"type": "report", "summary": "s"})
        self.assertEqual(title(), "generated")
        with t.open("a", encoding="utf-8") as f:
            f.write(rec("custom-title", "customTitle", "名前" + "x" * 100) + rec("ai-title", "aiTitle", "later")
                    + rec("custom-title", "customTitle", None) + "[\"custom-title\"]\n")
        self.run_hook("stop", {"transcript_path": str(t), "stop_hook_active": True})
        self.assertEqual(title(), "名前" + "x" * 100)
        deliver("kid", start)  # A later report never replaces the name
        self.assertEqual(title(), "名前" + "x" * 100)
        with t.open("a", encoding="utf-8") as f:
            f.write(rec("custom-title", "customTitle", "renamed"))
        deliver("kid", {"type": "command", "actor": "parent", "note": "x"}, writer="parent")
        self.assertNotEqual(title(), "renamed")  # The parent does not speak for the child's name
        deliver("kid", {"type": "report", "summary": "s"})
        self.assertEqual(title(), "renamed")

    def test_linked_pull_request(self):
        t = self.dir / "t.jsonl"
        url = "https://github.com/o/r/pull/"
        rec = lambda n: json.dumps({"type": "pr-link", "prNumber": n, "prUrl": f"{url}{n}"}) + "\n"  # noqa: E731
        pr = lambda: schema.fold(self.store.read("kid"))["pr"]  # noqa: E731

        t.write_text('{"type": "user", "text": "pr-link"}\n')
        self.run_hook("stop", {"transcript_path": str(t), "stop_hook_active": True})
        self.assertEqual(pr(), {})
        with t.open("a") as f:
            f.write(rec(7) + 'broken "pr-link"\n["pr-link"]\n{"type": "pr-link", "prNumber": 9}\n')
        deliver("kid", {"type": "report", "summary": "s"}, writer="parent")
        self.assertEqual(pr(), {})  # The parent does not speak for the child's pull request
        self.run_hook("stop", {"transcript_path": str(t), "stop_hook_active": True})
        self.assertEqual(pr(), {"number": 7, "url": url + "7"})
        deliver("kid", {"type": "pr", "pr": {"ci": "pass"}})
        self.assertEqual(pr(), {"number": 7, "url": url + "7", "ci": "pass"})
        with t.open("a") as f:
            f.write(rec(8))
        deliver("kid", {"type": "pr", "pr": {"ci": "pending"}})  # A new link drops the old CI facts
        self.assertEqual(pr(), {"number": 8, "url": url + "8", "ci": "pending"})
        deliver("kid", {"type": "pr", "pr": {"number": 7}})  # A report replaces an unchanged link
        self.run_hook("stop", {"transcript_path": str(t), "stop_hook_active": True})
        self.assertEqual(pr(), {"number": 7})
        deliver("kid", {"type": "pr", "pr": {"number": 8}})  # The linked number gets its URL back
        self.assertEqual(pr(), {"number": 8, "url": url + "8"})

    def test_malformed_pr_link_is_dropped(self):
        for link in ("x", {"number": 1}, {"number": "1", "url": "https://h/1"}, {"number": True, "url": "https://h/1"},
                     {"number": 1, "url": "javascript:alert(1)"}, {"number": 1, "url": "https://h/" + "x" * 500}):
            ev = core.record(self.store, "kid", {"type": "report", "pr_link": link})["event"]
            self.assertNotIn("pr_link", ev)

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


@unittest.skipUnless(shutil.which("curl"), "the launcher checks the hub with curl")
class LauncherTest(TmpMixin, unittest.TestCase):
    """`Session Hub.command`: the settings it resolves decide which hub it opens."""

    LAUNCHER = Path(__file__).resolve().parent.parent / "Session Hub.command"

    def setUp(self):
        super().setUp()
        self.httpd, _ = make_server(self.store, port=0, token="a+b&c")
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.home = self.dir / "home"
        (self.home / ".claude").mkdir(parents=True)
        stub = self.dir / "bin" / "open"
        stub.parent.mkdir()
        self.opened = self.dir / "opened"
        stub.write_text(f'#!/bin/sh\necho "$1" >> "{self.opened}"\n')
        stub.chmod(0o755)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def launch(self, settings_env: dict, **env) -> str:
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"env": settings_env}))
        clean = {k: v for k, v in os.environ.items() if not k.startswith("HUB_")}
        clean.update(HOME=str(self.home), PATH=f"{self.dir / 'bin'}:{os.environ['PATH']}", **env)
        proc = subprocess.Popen(["sh", str(self.LAUNCHER)], env=clean, cwd=self.dir, start_new_session=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 15
            while not self.opened.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(1.5)  # Past the first health check of the waiting loop
            self.assertIsNone(proc.poll(), "the launcher must stay until Ctrl-C")
            os.killpg(proc.pid, signal.SIGINT)  # As Ctrl-C does: the whole foreground group
            out, _ = proc.communicate(timeout=20)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("stopped the hub", out)
        self.assertFalse(client.healthy(f"http://127.0.0.1:{self.port}"))
        return self.opened.read_text().strip()

    def test_reads_settings_json_and_opens_the_running_hub(self):
        # An IPv6 loopback URL with an uppercase scheme, and a token that needs percent-encoding
        opened = self.launch({"HUB_STORE": "~/store", "HUB_URL": f"HTTP://[::1]:{self.port}",
                              "HUB_TOKEN": "a+b&c"})
        self.assertEqual(opened, f"http://127.0.0.1:{self.port}/?token={urllib.parse.quote('a+b&c', safe='')}")

    def test_shell_environment_wins_over_settings_json(self):
        opened = self.launch({"HUB_URL": "http://127.0.0.1:1", "HUB_TOKEN": "wrong"},
                             HUB_URL=f"http://127.0.0.1:{self.port}", HUB_TOKEN="a+b&c")
        self.assertEqual(opened, f"http://127.0.0.1:{self.port}/?token=a%2Bb%26c")


if __name__ == "__main__":
    unittest.main()
