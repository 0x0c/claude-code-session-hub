"""The hook handlers: session start, the server autostart, the task sync, and the failure paths."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from session_hub import hooks, local_state, schema
from session_hub.deliver import deliver
from session_hub.store import EventStore


class HooksCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.store = EventStore(self.dir / "store")
        self.home = self.dir / "home"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HUB_", "CLAUDE_CODE_"))}
        env.update(HUB_STORE=str(self.store.root), HUB_SESSION_ID="kid", HOME=str(self.home),
                   HUB_STATE_DIR=str(self.dir / "state"))
        patch = mock.patch.dict(os.environ, env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def run_hook(self, name, stdin="{}"):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(out), redirect_stderr(err):
            hooks.run(name)  # Must never raise
        return out.getvalue().strip(), err.getvalue().strip()


class SessionStartTest(HooksCase):
    def test_the_message_depends_on_the_registration(self):
        self.assertIn("Not registered yet", self.run_hook("session-start")[0])
        deliver("kid", {"type": "start", "title": "T", "state": "working"})
        self.assertIn("Last report: state=working", self.run_hook("session-start")[0])

    def test_the_message_is_short(self):
        self.assertLessEqual(len(self.run_hook("session-start")[0].splitlines()), 2)

    def test_nothing_is_printed_without_configuration(self):
        del os.environ["HUB_STORE"]
        self.assertEqual(self.run_hook("session-start"), ("", ""))

    def test_the_shim_is_installed_and_repaired(self):
        shim = hooks.install_shim()
        self.assertEqual(shim, self.home / ".local" / "bin" / "session-hub")
        self.assertTrue(os.access(shim, os.X_OK))
        content = shim.read_text()
        self.assertIn(str(hooks.PLUGIN_ROOT / "bin" / "session-hub"), content)
        shim.write_text("stale")
        hooks.install_shim()
        self.assertEqual(shim.read_text(), content)

    def test_the_shim_is_optional(self):
        with mock.patch.object(hooks, "PLUGIN_ROOT", self.dir):
            self.assertIsNone(hooks.install_shim())
        self.home.write_text("a file where the folder belongs")
        self.assertIsNone(hooks.install_shim())

    def test_the_command_is_absolute_when_the_shim_is_not_on_the_path(self):
        shim = self.home / ".local" / "bin"
        os.environ["PATH"] = "/usr/bin"
        self.assertIn(f"`{shim}/session-hub`", self.run_hook("session-start")[0])
        os.environ["PATH"] = f"/usr/bin:{shim}"
        self.assertIn("report with `session-hub`", self.run_hook("session-start")[0])

    def test_a_failing_autostart_does_not_hide_the_message(self):
        with mock.patch.object(hooks, "autostart_server", side_effect=OSError("no")):
            out, err = self.run_hook("session-start")
        self.assertIn("session_id=kid", out)
        self.assertIn("could not start the server", err)


class AutostartTest(HooksCase):
    def setUp(self):
        super().setUp()
        os.environ.update(HUB_AUTOSTART="1", HUB_URL="http://127.0.0.1:9999")

    def test_it_starts_the_hub_when_none_answers(self):
        with mock.patch.object(hooks.client, "healthy", return_value=False), \
                mock.patch.object(hooks.subprocess, "Popen") as popen:
            self.assertEqual(hooks.autostart_server(), "started")
        self.assertEqual(popen.call_args.args[0], [sys.executable, "-m", "session_hub", "serve", "--host", "127.0.0.1",
                                                   "--port", "9999"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertTrue(popen.call_args.kwargs["env"]["PYTHONPATH"].startswith(str(hooks.PLUGIN_ROOT)))

    def test_it_leaves_a_running_hub_alone(self):
        with mock.patch.object(hooks.client, "healthy", return_value=True), \
                mock.patch.object(hooks.subprocess, "Popen") as popen:
            self.assertEqual(hooks.autostart_server(), "running")
        popen.assert_not_called()

    def test_it_runs_for_local_use_alone(self):
        for change in ({"HUB_AUTOSTART": "0"}, {"HUB_URL": "http://hub.example:8765"}, {"HUB_URL": ""},
                       {"HUB_STORE": ""}):
            with self.subTest(change), mock.patch.dict(os.environ, change), \
                    mock.patch.object(hooks.subprocess, "Popen") as popen:
                self.assertIsNone(hooks.autostart_server())
                popen.assert_not_called()


class StopTest(HooksCase):
    def test_the_guard_can_be_turned_off(self):
        os.environ["HUB_STOP_GUARD"] = "0"
        self.assertEqual(self.run_hook("stop"), ("", ""))
        self.assertEqual(self.store.read("kid")[-1]["type"], "heartbeat")  # The heartbeat still goes out

    def test_a_waiting_state_may_stop(self):
        for state in ("waiting_ci", "blocked", "queued"):
            deliver("kid", {"type": "report", "state": state})
            self.assertEqual(self.run_hook("stop")[0], "", state)

    def test_a_session_without_an_id_is_left_alone(self):
        del os.environ["HUB_SESSION_ID"]
        for name in ("stop", "todo"):
            self.assertEqual(self.run_hook(name), ("", ""))
        self.assertIsNone(hooks.send({"type": "heartbeat"}))
        self.assertEqual(self.store.session_ids(), [])


class FailureTest(HooksCase):
    def test_unreadable_input_counts_as_empty(self):
        for stdin in ("", "  ", "not json"):
            self.assertIn("session_id=kid", self.run_hook("session-start", stdin)[0])

    def test_an_exception_is_reported_and_swallowed(self):
        with mock.patch.dict(hooks.HANDLERS, {"stop": mock.Mock(side_effect=RuntimeError("boom"))}):
            self.assertEqual(self.run_hook("stop"), ("", "session-hub hook stop: boom"))
        self.assertEqual(self.run_hook("stop", "[]")[0], "")  # The payload is not an object

    def test_a_rejected_event_is_swallowed(self):
        self.assertIsNone(hooks.send({"type": "no-such-type"}))


class TodoTest(HooksCase):
    def todo(self, tool, inp, resp=None):
        self.run_hook("todo", json.dumps({"tool_name": tool, "tool_input": inp, "tool_response": resp}))

    def status(self):
        return schema.fold(self.store.read("kid"))

    def tasks(self):
        return [(t["t"], t["s"]) for t in self.status()["tasks"]]

    def test_statuses_are_mapped(self):
        self.todo("TodoWrite", {"todos": [{"content": f"n{i}", "status": s} for i, s in enumerate(
            ("pending", "in_progress", "completed", "cancelled", "deleted", "unknown"))]})
        self.assertEqual(self.tasks(), [("n0", "todo"), ("n1", "doing"), ("n2", "done"), ("n3", "skip"), ("n5", "todo")])

    def test_an_unnamed_todo_does_not_lose_the_others(self):
        self.todo("TodoWrite", {"todos": [{"content": " ", "status": "pending"}, {"content": "a", "status": "pending"}]})
        self.assertEqual(self.tasks(), [("a", "todo")])

    def test_a_task_is_renamed_started_and_deleted(self):
        self.todo("TaskCreate", {"subject": "old  name=x"}, "Task #4 created")
        self.assertEqual(self.tasks(), [("old name＝x", "todo")])
        self.todo("TaskUpdate", {"taskId": 4, "status": "in_progress", "subject": "new", "activeForm": "Doing it"})
        self.assertEqual(self.tasks(), [("new", "doing")])
        self.assertEqual((self.status()["state"], self.status()["summary"]), ("working", "Doing it"))
        self.todo("TaskUpdate", {"taskId": "4", "status": "deleted"})
        self.assertEqual(self.tasks(), [])

    def test_a_started_task_never_overrides_a_question(self):
        deliver("kid", {"type": "ask", "attention": {"kind": "decision", "question": "q?"}})
        self.todo("TodoWrite", {"todos": [{"content": "a", "status": "in_progress"}]})
        self.assertEqual(self.status()["state"], "needs_human")

    def test_other_calls_send_nothing(self):
        self.todo("Bash", {"command": "ls"})
        self.todo("TaskUpdate", {"taskId": "unknown", "status": "completed"})
        self.todo("TaskCreate", {})
        self.todo("TodoWrite", {"todos": "x"})
        self.todo("TodoWrite", "x")
        self.assertEqual(self.store.session_ids(), [])

    def test_the_task_id_is_found_in_any_shape(self):
        for resp, want in (({"task": {"id": 9}}, "9"), ([{"taskId": "a"}], "a"), ({"x": ["Task #12 created"]}, "12"),
                           ('{"id": "t7"}', "t7"), ("done", None), ([], None), (None, None)):
            with self.subTest(resp):
                self.assertEqual(hooks._find_task_id(resp), want)


class LocalStateTest(HooksCase):
    def test_a_corrupt_file_reads_as_empty(self):
        local_state.save("kid", {"state": "working"})
        self.assertEqual(local_state.load("kid"), {"state": "working"})
        next((self.dir / "state").glob("*.json")).write_text("{")
        self.assertEqual(local_state.load("kid"), {})

    def test_an_unwritable_folder_is_ignored(self):
        (self.dir / "state").write_text("a file where the folder belongs")
        local_state.save("kid", {"state": "working"})
        self.assertEqual(local_state.load("kid"), {})

    def test_the_state_of_an_unsent_event_is_derived(self):
        for fields, want in (({"type": "start"}, "planning"), ({"type": "report", "state": "blocked"}, "blocked"),
                             ({"type": "ask"}, "needs_human"), ({"type": "ready"}, "review_ready"),
                             ({"type": "fail"}, "failed"), ({"type": "done"}, "done"), ({"type": "report"}, "done")):
            local_state.note("kid", fields, None)
            self.assertEqual(local_state.load("kid")["state"], want)

    def test_a_hook_does_not_register_the_session(self):
        local_state.note("kid", {"type": "heartbeat", "actor": "hook"}, None)
        self.assertNotIn("started", local_state.load("kid"))


if __name__ == "__main__":
    unittest.main()
