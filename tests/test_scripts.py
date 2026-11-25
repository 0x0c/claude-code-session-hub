"""The development scripts that no other test covers: the demo data, the playbook file, and the launchers."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from session_hub import view
from session_hub.store import EventStore

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import demo  # noqa: E402


class ScriptsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_command(self, *argv, stdin=""):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HUB_", "CLAUDE_CODE_"))}
        env.update(HOME=str(self.dir / "home"))
        return subprocess.run([str(a) for a in argv], env=env, cwd=self.dir, input=stdin, capture_output=True,
                              text=True, encoding="utf-8", timeout=30)

    def test_the_demo_shows_every_kind_of_session_in_both_languages(self):
        self.assertEqual(set(demo.TEXT["en"]), set(demo.TEXT["ja"]))
        for lang in demo.TEXT:
            store = EventStore(self.dir / lang)
            demo.seed(store, lang)
            snap = view.store_snapshot(store)
            self.assertEqual(sorted(view.state_code(s) for s in snap["sessions"]),
                             ["AR", "FL", "NH", "RR", "ST", "WK"], lang)
            self.assertEqual(snap["collections"]["knowledge"]["active"], 5, lang)

    def test_the_demo_command_replaces_the_old_events(self):
        for _ in range(2):
            res = self.run_command(sys.executable, ROOT / "scripts" / "demo.py", "--store", "demo", "--lang", "en")
            self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(len(EventStore(self.dir / "demo").read("session_04DepsBump")), 3)

    def test_the_playbook_command_writes_the_page(self):
        res = self.run_command(sys.executable, ROOT / "scripts" / "playbook.py", "--out", "p.html")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("<html", (self.dir / "p.html").read_text(encoding="utf-8"))

    def test_the_wrapper_finds_the_package_from_any_folder(self):
        res = self.run_command(ROOT / "bin" / "session-hub", "--store", "s", "status", "--json")
        self.assertEqual((res.returncode, json.loads(res.stdout)), (0, []), res.stderr)

    def test_an_unconfigured_hook_is_silent(self):
        for name in ("session-start", "stop", "todo"):
            res = self.run_command(ROOT / "bin" / "session-hub", "hook", name, stdin="not json")
            self.assertEqual((res.returncode, res.stdout), (0, ""), res.stderr)

    def test_every_hook_command_names_a_known_hook(self):
        text = (ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        from session_hub.hooks import HANDLERS
        commands = [h["command"] for groups in json.loads(text)["hooks"].values() for g in groups for h in g["hooks"]]
        names = {c.split(" hook ")[1].split()[0].strip('"') for c in commands}
        self.assertEqual(names, set(HANDLERS))


if __name__ == "__main__":
    unittest.main()
