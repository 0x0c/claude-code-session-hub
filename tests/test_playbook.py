import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from session_hub import playbook
from session_hub.server import make_server
from session_hub.store import EventStore


class PlaybookTest(unittest.TestCase):
    def test_build_adds_the_stories_inside_the_dashboard_script(self):
        html = playbook.playbook_html()
        self.assertEqual(html.count("<script>"), 1)
        stories = html.index("const PB = [")
        self.assertLess(html.index("function sessionCard"), stories)
        self.assertLess(stories, html.rindex("})();\n</script>"))

    def test_build_is_static(self):
        html = playbook.playbook_html()
        self.assertIn(f"const EMBEDDED = {playbook.EMPTY};", html)

    def test_build_stops_when_the_dashboard_lost_an_insertion_point(self):
        page = playbook.dashboard_html()
        for point in (playbook.SNAPSHOT, playbook.END, "</head>"):
            with self.subTest(point=point), mock.patch.object(playbook, "dashboard_html", lambda: page.replace(point, "")):
                with self.assertRaises(ValueError):
                    playbook.playbook_html()

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_page_script_parses(self):
        script = re.search(r"<script>\n(.*)</script>", playbook.playbook_html(), re.S)[1]
        check = subprocess.run(["node", "--check", "-"], input=script, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_stories_call_functions_that_the_dashboard_defines(self):
        page = playbook.dashboard_html()
        stories = playbook.template("playbook.js")
        for name in set(re.findall(r"\b(render[A-Z]\w*|sessionCard|eventRow|knowledgeCard|markGlow|badge)\b", stories)):
            with self.subTest(name=name):
                self.assertRegex(page, rf"(function|const) {name}\b")

    def test_playbook_classes_do_not_clash_with_the_dashboard(self):
        style = playbook.template("playbook.css")
        style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        for name in re.findall(r"\.([a-z][\w-]*)", style):
            self.assertTrue(name.startswith("pb-"), name)

    def test_hub_serves_the_playbook_behind_its_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, hub = make_server(EventStore(Path(tmp) / "store"), port=0, token="secret")
            url = f"http://127.0.0.1:{server.server_address[1]}"
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(f"{url}/playbook", timeout=5)
                self.assertEqual(denied.exception.code, 401)
                denied.exception.close()
                with urllib.request.build_opener(urllib.request.HTTPCookieProcessor()).open(f"{url}/playbook?token=secret", timeout=5) as res:
                    self.assertEqual(res.geturl(), f"{url}/playbook")
                req = urllib.request.Request(f"{url}/playbook", headers={"Authorization": "Bearer secret"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    self.assertEqual(res.read().decode("utf-8"), playbook.playbook_html())
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()

    def test_dashboard_links_to_the_playbook(self):
        self.assertIn('href="playbook"', playbook.dashboard_html())


if __name__ == "__main__":
    unittest.main()
