import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from session_hub import schema, view
from session_hub.guide import guide_html
from session_hub.playbook import dashboard_html, template
from session_hub.server import make_server
from session_hub.store import EventStore

PAGE = dashboard_html()
LANGS = [re.search(rf"^    {lang}: \{{\n(.*?)^    \}},$", PAGE, re.M | re.S)[1] for lang in ("en", "ja")]
COLORED = set(re.findall(r"(\w+): \"--s-", re.search(r"const STATE_COLORS = \{(.*?)\};", PAGE, re.S)[1]))
STATUS_STATES = {status: re.findall(r'"(\w+)"', states) for status, states in
                 re.findall(r"(\w+): \[([^\]]*)\]", re.search(r"const STATUS_STATES = \{(.*?)\};", PAGE, re.S)[1])}


class GuideTest(unittest.TestCase):
    def test_every_state_belongs_to_one_status(self):
        listed = [s for states in STATUS_STATES.values() for s in states]
        self.assertEqual(sorted(listed), sorted(COLORED))
        self.assertLessEqual(set(schema.STATES), set(listed))

    def test_every_status_and_state_is_explained_in_both_languages(self):
        for key in [f"group.{s}" for s in STATUS_STATES] + [f"state.{s}" for s in COLORED]:
            for messages in LANGS:
                self.assertIn(f'"help.{key}": "', messages)

    def test_the_guide_agrees_with_what_needs_action(self):
        now = datetime.now(timezone.utc)

        def needs_action(state, minutes=0, gate_met=True):
            ev = {"session_id": "s", "seq": 1, "type": "report", "state": state, "actor": "child",
                  "ts": (now - timedelta(minutes=minutes)).isoformat()}
            if gate_met:
                ev |= {"pr": {"number": 1, "ci": "pass"},
                       "ready": {"self_review": True, "tests_added": True, "description": True}}
            return view.session_view([ev], now)[0]["needs_action"]

        for state in schema.STATES:
            with self.subTest(state=state):
                self.assertEqual(needs_action(state), state in STATUS_STATES["action"])
        self.assertFalse(needs_action("review_ready", gate_met=False))  # review_pending
        for state in ("planning", "working"):  # stale
            self.assertTrue(needs_action(state, view.STALE_MINUTES))

    def test_the_guide_names_the_stale_period(self):
        for messages in LANGS:
            self.assertIn(str(view.STALE_MINUTES), re.search(r'"help.state.stale": "([^"]*)"', messages)[1])

    def test_dashboard_shows_the_help_icons_and_links_to_the_guide(self):
        self.assertIn('help("group." + status)', PAGE)
        self.assertIn('help("state." + stateKey(s))', PAGE)
        self.assertIn('href="guide"', PAGE)

    def test_guide_classes_do_not_clash_with_the_dashboard(self):
        style = re.sub(r"/\*.*?\*/", "", template("guide.css"), flags=re.S)
        for name in re.findall(r"\.([a-z][\w-]*)", style):
            self.assertTrue(name.startswith("gd-"), name)

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_page_script_parses(self):
        script = re.search(r"<script>\n(.*)</script>", guide_html(), re.S)[1]
        check = subprocess.run(["node", "--check", "-"], input=script, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_hub_serves_the_guide_behind_its_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, hub = make_server(EventStore(Path(tmp) / "store"), port=0, token="secret")
            url = f"http://127.0.0.1:{server.server_address[1]}/guide"
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(url, timeout=5)
                self.assertEqual(denied.exception.code, 401)
                denied.exception.close()
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
                with opener.open(f"{url}?token=secret", timeout=5) as res:
                    self.assertEqual(res.geturl(), url)
                    self.assertEqual(res.read().decode("utf-8"), guide_html())
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
