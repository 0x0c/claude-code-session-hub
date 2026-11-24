"""The session-hub command, run in process against a temporary store."""

import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from session_hub import cli, client, schema
from session_hub.server import make_server
from session_hub.store import EventStore


class CliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.store = EventStore(self.dir / "store")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HUB_", "CLAUDE_CODE_"))}
        env.update(HUB_STORE=str(self.store.root), HUB_SESSION_ID="kid", HOME=str(self.dir / "home"),
                   HUB_STATE_DIR=str(self.dir / "state"), HUB_OUTBOX=str(self.dir / "outbox.jsonl"))
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def run_cli(self, *argv, stdin=""):
        """Return (exit code or message, stdout, stderr)."""
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
            try:
                cli.main(list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue().strip(), err.getvalue().strip()

    def ok(self, *argv, stdin=""):
        code, out, err = self.run_cli(*argv, stdin=stdin)
        self.assertEqual(code, 0, f"{argv}: {out} {err}")
        return out

    def status(self, sid="kid"):
        return schema.fold(self.store.read(sid))

    def serve(self, **kw):
        httpd, _ = make_server(self.store, port=0, **kw)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        os.environ["HUB_URL"] = f"http://127.0.0.1:{httpd.server_address[1]}"


class ChildCommandTest(CliCase):
    def test_a_session_from_start_to_done(self):
        self.ok("start", "--title", "T", "--task", "a=doing:S", "--repo", "o/r", "--branch", "b")
        self.ok("report", "--state", "working", "--phase", "test", "--confidence", "high", "--task", "a=done")
        st = self.status()
        self.assertEqual((st["title"], st["repo"], st["branch"], st["state"], st["phase"], st["confidence"]),
                         ("T", "o/r", "b", "working", "test", "high"))
        self.assertEqual(st["progress"], {"done": 1, "total": 1, "remaining": 0})
        out = self.ok("done", "--summary", "finished")
        self.assertEqual(out, "[HUB/1] kid done finished")

    def test_a_report_without_a_field_is_refused(self):
        code, _, _ = self.run_cli("report")
        self.assertIn("at least one field", code)
        self.assertEqual(self.store.read("kid"), [])

    def test_ask_and_answer(self):
        self.ok("start", "--title", "T")
        self.ok("ask", "--kind", "decision", "--q", "q?", "--opt", "x", "--opt", "y", "--default", "x")
        att = self.status()["attention"]
        self.assertEqual((att["options"], att["default"], att["blocking"]), (["x", "y"], "x", True))
        out = self.ok("answer", "kid", "--qid", str(att["qid"]), "--value", "y")
        self.assertIn(f"[HUB/1] cmd=answer q={att['qid']} v=y", out.splitlines())
        self.assertEqual((self.status()["attention"], self.status()["state"]), (None, "working"))
        self.ok("ask", "--kind", "decision", "--q", "q?", "--non-blocking")
        self.assertFalse(self.status()["attention"]["blocking"])

    def test_command_goes_to_the_parent_file(self):
        self.ok("start", "--title", "T")
        out = self.ok("command", "kid", "--cmd", "pause", "--arg", "now")
        self.assertIn("[HUB/1] cmd=pause now", out)
        ev = self.store.read("kid")[-1]
        self.assertEqual((ev["writer"], ev["note"], ev["actor"]), ("parent", "pause now", "parent"))

    def test_pr_and_ready_pass_the_gate(self):
        self.ok("start", "--title", "T")
        self.ok("pr", "--number", "3", "--url", "https://h/3", "--ci", "pass", "--mergeable", "yes", "--threads", "0",
                "--state", "waiting_ci")
        st = self.status()
        self.assertEqual((st["state"], st["pr"]), ("waiting_ci", {
            "number": 3, "url": "https://h/3", "ci": "pass", "mergeable": True, "unresolved_threads": 0}))
        self.assertIn("gate is not met", self.ok("ready"))
        self.ok("report", "--state", "working")
        out = self.ok("ready", "--self-review", "--tests", "--description", "--summary", "look")
        self.assertEqual(out, "[HUB/1] kid review_ready PR#3 ci=pass look")

    def test_mergeable_accepts_a_negative_answer(self):
        self.ok("pr", "--number", "3", "--mergeable", "false")
        self.assertIs(self.status()["pr"]["mergeable"], False)

    def test_fail_records_the_error(self):
        self.assertEqual(self.ok("fail", "--error", "boom"), "[HUB/1] kid failed boom")
        self.assertEqual(self.status()["last_error"], "boom")

    def test_quiet_prints_nothing_but_an_escalation(self):
        self.assertEqual(self.ok("-q", "start", "--title", "T"), "")
        self.assertTrue(self.ok("-q", "done").startswith("[HUB/1]"))

    def test_heartbeat_reads_usage_from_either_source(self):
        t = self.dir / "t.jsonl"
        t.write_text(json.dumps({"message": {"id": "a", "role": "assistant", "usage": {"input_tokens": 7}}}) + "\n")
        self.assertEqual(self.ok("heartbeat", "--transcript", str(t), "--cost", "1.5", "--context-pct", "40"), "")
        usage = self.status()["usage"]
        self.assertEqual((usage["input"], usage["cost_usd"], usage["context_pct"]), (7, 1.5, 40))
        self.ok("--session", "other", "heartbeat", stdin=json.dumps({"transcript_path": str(t)}))
        self.assertEqual(self.status("other")["usage"]["input"], 7)
        self.ok("--session", "broken", "heartbeat", stdin="not json")
        self.assertEqual(self.status("broken")["usage"], {})

    def test_the_session_id_is_required(self):
        del os.environ["HUB_SESSION_ID"]
        code, _, _ = self.run_cli("start", "--title", "T")
        self.assertIn("cannot tell the session ID", code)
        self.ok("--session", "named", "start", "--title", "T")
        self.assertEqual(self.store.session_ids(), ["named"])

    def test_invalid_input_exits_with_a_message(self):
        code, _, _ = self.run_cli("--session", "../evil", "start", "--title", "T")
        self.assertIn("not allowed", code)
        code, _, _ = self.run_cli("report", "--task", "=done")
        self.assertIn("missing task name", code)

    def test_an_unreachable_hub_falls_back_and_says_so(self):
        os.environ["HUB_URL"] = "http://127.0.0.1:1"
        _, _, err = self.run_cli("start", "--title", "T")
        self.assertIn("wrote the event to the shared store", err)
        self.assertEqual(self.status()["title"], "T")
        del os.environ["HUB_STORE"]
        code, out, err = self.run_cli("report", "--summary", "s")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("saved the event to the outbox", err)

    def test_flush_sends_the_outbox(self):
        self.assertIn("HUB_URL is not set", self.run_cli("flush")[0])
        self.serve()
        client.spool({"session_id": "kid", "fields": {"type": "start", "title": "queued"}})
        self.assertEqual(self.ok("flush"), "sent 1")
        self.assertEqual(self.status()["title"], "queued")

    def test_a_failed_git_push_warns_but_keeps_the_event(self):
        with mock.patch.object(EventStore, "is_git", return_value=True), \
                mock.patch.object(EventStore, "sync", return_value=False) as sync:
            code, _, err = self.run_cli("start", "--title", "T")
            self.assertEqual((code, sync.call_count), (0, 1))
            self.assertIn("git push failed", err)
            self.run_cli("--no-sync", "report", "--summary", "s")
            self.assertEqual(sync.call_count, 1)
        self.assertEqual(len(self.store.read("kid")), 2)


class ReadCommandTest(CliCase):
    def test_attention_status_and_log(self):
        self.assertEqual(self.ok("attention"), "(nothing needs action)")
        self.ok("start", "--title", "T", "--task", "a=done")
        self.ok("heartbeat")
        self.ok("--session", "bad", "fail", "--error", "boom")
        self.assertEqual(self.ok("attention"), "FL bad boom")
        rows = self.ok("status").splitlines()
        self.assertEqual([r.split()[:2] for r in rows], [["FL", "bad"], ["PL", "kid"]])
        self.assertIn("1/1 T", rows[1])
        self.assertEqual([s["session_id"] for s in json.loads(self.ok("status", "--json"))], ["bad", "kid"])
        self.assertEqual(len(self.ok("log").splitlines()), 2)
        self.assertEqual(len(self.ok("log", "--heartbeat").splitlines()), 3)
        self.assertIn(" bad ", self.ok("log", "--tail", "1"))
        self.assertIn("state:queued→planning", self.ok("log", "kid"))

    def test_learn_knowledge_and_collection(self):
        self.ok("learn", "--kind", "caveat", "--title", "Old Redis", "--body", "sort", "--tag", "CI", "--scope", "tests/")
        self.assertEqual(self.ok("knowledge", "--body"), "[caveat] Old Redis (#ci @tests/)\n    sort")
        self.assertEqual(self.ok("knowledge", "--kind", "howto"), "(no matches)")
        self.assertIn("### Old Redis", self.ok("collection", "knowledge"))
        self.assertIn("## 注意点", self.ok("collection", "knowledge", "--lang", "ja"))
        col = json.loads(self.ok("collection", "knowledge", "--format", "json"))
        self.assertEqual(col["items"][0]["title"], "Old Redis")
        self.ok("learn", "--kind", "caveat", "--title", "Old Redis", "--obsolete")
        self.assertEqual(self.ok("knowledge"), "(no matches)")
        self.assertIn("available: knowledge", self.run_cli("collection", "nope")[0])

    def test_a_broken_collections_file_exits_with_a_message(self):
        self.ok("start", "--title", "T")
        (self.store.root / "collections.json").write_text("{")
        self.assertIn("cannot read collections.json", self.run_cli("status")[0])

    def test_reads_come_from_the_running_hub(self):
        self.serve(token="t")
        os.environ["HUB_TOKEN"] = "t"
        self.ok("start", "--title", "pushed")
        os.environ["HUB_STORE"] = str(self.dir / "empty")
        self.assertIn("pushed", self.ok("status"))
        os.environ["HUB_URL"] = "http://127.0.0.1:1"
        self.assertIn("unreachable", self.run_cli("status")[0])

    def test_pull_updates_the_store_first(self):
        with mock.patch.object(EventStore, "pull") as pull:
            self.ok("status")
            pull.assert_not_called()
            self.ok("status", "--pull")
            pull.assert_called_once_with()

    def test_export_embeds_a_snapshot_that_cannot_close_the_script(self):
        self.ok("start", "--title", "</script><b>x")
        page = self.dir / "out.html"
        self.assertEqual(self.ok("export", "--out", str(page)), f"wrote {page}")
        html = page.read_text(encoding="utf-8")
        self.assertIn("<\\/script><b>x", html)
        self.assertNotIn("</script><b>x", html)
        self.assertNotIn("/*__HUB_SNAPSHOT__*/null", html)

    def test_serve_passes_its_options(self):
        with mock.patch("session_hub.server.serve") as serve:
            self.ok("serve", "--port", "1234", "--watch-files", "--pull-every", "5")
        self.assertEqual(serve.call_args.kwargs, {"host": "127.0.0.1", "port": 1234, "token": None,
                                                  "watch_files": True, "pull_every": 5.0})

    def test_the_hook_command_runs_the_named_hook(self):
        out = self.ok("hook", "session-start", stdin="{}")
        self.assertIn("session_id=kid", out)


class DoctorTest(CliCase):
    def test_a_local_store_is_enough(self):
        out = self.ok("doctor")
        self.assertIn("OK  Session ID: kid", out)
        self.assertIn("--  HUB_URL: not set", out)
        self.assertIn("not created yet", out)

    def test_no_session_and_no_store_is_a_problem(self):
        del os.environ["HUB_STORE"], os.environ["HUB_SESSION_ID"]
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("NG  Session ID: unknown", out)
        self.assertIn("NG  HUB_STORE: not set", out)

    def test_a_stopped_hub_is_a_problem_without_a_shared_store(self):
        os.environ["HUB_URL"] = "http://127.0.0.1:1"
        self.assertIn("--  Hub server: not responding", self.ok("doctor"))
        del os.environ["HUB_STORE"]
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("NG  Hub server: not responding", out)

    def test_the_token_is_checked(self):
        self.serve(token="t")
        code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("NG  Authentication", out)
        os.environ["HUB_TOKEN"] = "t"
        self.assertIn("OK  Authentication: OK", self.ok("doctor"))

    def test_the_outbox_is_counted(self):
        client.spool({"session_id": "kid", "fields": {}})
        self.assertIn("--  Unsent events in the outbox: 1", self.ok("doctor"))


if __name__ == "__main__":
    unittest.main()
