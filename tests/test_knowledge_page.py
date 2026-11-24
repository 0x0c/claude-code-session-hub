"""The knowledge summary page served at /knowledge."""

import re
import tempfile
import threading
import unittest
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

    def test_dashboard_links_to_the_page_in_both_languages(self):
        page = dashboard_html()
        self.assertIn('href="knowledge"', page)
        for key in ("btn.knowledge", "btn.knowledgeTitle", "kn.title", "kn.sec.shared", "kn.sharedLead"):
            self.assertEqual(len(re.findall(rf'"{re.escape(key)}":', page)), 2, key)  # English and Japanese

    def test_exported_file_hides_the_link(self):
        self.assertIn('$("knowledgeLink").hidden', dashboard_html())

    def test_page_is_the_dashboard_with_the_added_script(self):
        page = knowledge_html()
        self.assertIn(template("knowledge.js").strip(), page)
        self.assertIn(".kn-main", page)

    def test_knowledge_classes_do_not_clash_with_the_dashboard(self):
        style = re.sub(r"/\*.*?\*/", "", template("knowledge.css"), flags=re.S)
        for name in set(re.findall(r"\.([a-z][\w-]*)", style)):
            self.assertTrue(name.startswith("kn-"), name)

    def test_dashboard_opens_the_tab_named_by_the_hash(self):
        page = dashboard_html()
        self.assertIn('location.hash.startsWith("#col:")', page)
        # A reconnect's snapshot must not switch the reader back, so the hash is dropped once applied
        self.assertRegex(page, r'setView\(location\.hash\.slice\(1\)\);\s*history\.replaceState\(')


if __name__ == "__main__":
    unittest.main()
