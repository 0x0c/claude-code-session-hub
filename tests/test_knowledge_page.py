"""The knowledge summary page served at /knowledge."""

import json
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import http.client
import urllib.error
import urllib.request
from pathlib import Path

from session_hub.knowledge import knowledge_html
from session_hub.playbook import template
from session_hub.server import dashboard_html, make_server
from session_hub.store import EventStore


def serve(tmp, token=None):
    server, hub = make_server(EventStore(Path(tmp) / "store"), port=0, token=token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hub, f"http://127.0.0.1:{server.server_address[1]}"


class KnowledgePageTest(unittest.TestCase):
    def test_hub_serves_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, hub, base = serve(tmp)
            try:
                with urllib.request.urlopen(base + "/knowledge", timeout=5) as res:
                    self.assertEqual(res.status, 200)
                    self.assertIn("text/html", res.headers["Content-Type"])
                    self.assertIn("knSummarize", res.read().decode("utf-8"))
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()

    def test_the_page_needs_the_token_when_one_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, hub, base = serve(tmp, token="secret")
            try:
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base + "/knowledge", timeout=5)
                self.assertEqual(ctx.exception.code, 401)
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()

    def test_token_in_the_url_becomes_a_cookie_and_the_page_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, hub, _ = serve(tmp, token="secret")
            try:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                conn.request("GET", "/knowledge?token=secret")
                res = conn.getresponse()
                self.assertEqual(res.status, 303)
                self.assertEqual(res.getheader("Location"), "/knowledge")
                self.assertTrue(res.getheader("Set-Cookie").startswith("hub_token="))
                conn.close()
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_page_script_parses(self):
        script = re.search(r"<script>\n(.*)</script>", knowledge_html(), re.S)[1]
        check = subprocess.run(["node", "--check", "-"], input=script, text=True, encoding="utf-8", capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_summary_counts_active_items_and_orders_them(self):
        js = template("knowledge.js")
        code = re.search(r"  const KN_LISTED.*?\n(?=  let knCol)", js, re.S)[0] + re.search(r"  function knSummarize.*?\n  }\n", js, re.S)[0]
        issue = lambda i: {"kind": "issue", "title": f"i{i}", "last_ts": f"2026-01-{i:02d}", "reporters": ["a"], "tags": ["x"], "key": f"i{i}"}
        col = {"view": {"order": ["issue", "caveat"]}, "items": [issue(i) for i in range(1, 13)] + [
            {"kind": "caveat", "title": "old", "status": "obsolete", "last_ts": "2026-02-01", "reporters": ["a", "b"], "tags": ["x"]},
            {"kind": "caveat", "title": "two", "last_ts": "2026-02-02", "reporters": ["a", "b"], "tags": ["y"]},
            {"kind": "caveat", "title": "three", "last_ts": "2026-02-03", "reporters": ["a", "b", "c"], "tags": []}]}
        out = subprocess.run(["node", "-e", code + f"const s = knSummarize({json.dumps(col)});"
                              "console.log(JSON.stringify({active: s.active.length, reporters: s.reporters, kinds: [...s.kinds],"
                              "order: s.order, issues: s.issues.length, first: s.issues[0].title, shared: s.shared.map((i) => i.title),"
                              "latest: s.latest.length, tags: s.tags}))"], capture_output=True, text=True, check=True).stdout
        got = json.loads(out)
        self.assertEqual(got["active"], 14)  # the obsolete item is left out
        self.assertEqual(got["reporters"], 3)
        self.assertEqual(got["kinds"], [["issue", 12], ["caveat", 2]])
        self.assertEqual(got["order"], ["issue", "caveat"])
        self.assertEqual((got["issues"], got["first"]), (12, "i12"))  # every open issue, newest first
        self.assertEqual(got["shared"], ["three", "two"])  # most reporters first
        self.assertEqual(got["latest"], 10)
        self.assertEqual(got["tags"][0], ["x", 12])

    def test_dashboard_links_to_the_page_in_both_languages(self):
        page = dashboard_html()
        self.assertIn('href="knowledge"', page)
        for key in ("kn.error", "kn.unauthorized", "btn.knowledge", "btn.knowledgeTitle", "kn.title", "kn.sec.shared", "kn.sharedLead"):
            self.assertEqual(len(re.findall(rf'"{re.escape(key)}":', page)), 2, key)  # English and Japanese

    def test_guide_page_shows_the_link(self):
        self.assertRegex(template("guide.js"), r'\$\("knowledgeLink"\)\.hidden = [^;\n]*= false;')

    def test_exported_file_hides_the_link(self):
        self.assertRegex(dashboard_html(), r'\$\("knowledgeLink"\)\.hidden = [^;\n]*= !!EMBEDDED;')

    def test_page_is_the_dashboard_with_the_added_script(self):
        page = knowledge_html()
        self.assertIn(template("knowledge.js").strip(), page)
        self.assertIn(".kn-main", page)

    def test_knowledge_classes_do_not_clash_with_the_dashboard(self):
        style = re.sub(r"/\*.*?\*/", "", template("knowledge.css"), flags=re.S)
        for name in set(re.findall(r"\.([a-z][\w-]*)", style)):
            self.assertTrue(name.startswith("kn-"), name)

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_dashboard_opens_the_tab_named_by_the_hash_once(self):
        code = re.search(r"  function openHashedTab\(.*?\n  }\n", dashboard_html(), re.S)[0]
        script = """
          const calls = [];
          const location = { hash: "#col:knowledge", pathname: "/", search: "?x=1" };
          const history = { replaceState: (_s, _t, url) => { calls.push(["url", url]); location.hash = ""; } };
          const setView = (v) => calls.push(["view", v]);
          openHashedTab(false); openHashedTab(true); openHashedTab(true);
          location.hash = "#other"; openHashedTab(true);
          console.log(JSON.stringify(calls));
        """
        out = subprocess.run(["node", "-e", code + script], capture_output=True, text=True, check=True).stdout
        # Only the first snapshot applies the hash, and it clears the hash so that a reconnect does not repeat it
        self.assertEqual(json.loads(out), [["view", "col:knowledge"], ["url", "/?x=1"]])


if __name__ == "__main__":
    unittest.main()
