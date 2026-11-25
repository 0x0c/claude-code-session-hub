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
                    self.assertIn("knFilter", res.read().decode("utf-8"))
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

    def helpers(self, expr):
        js = template("knowledge.js")
        code = re.search(r"  const KN_PAGE.*?  // ---- End of the pure helpers ----", js, re.S)[0]
        return json.loads(subprocess.run(["node", "-e", code + f"\nconsole.log(JSON.stringify({expr}))"],
                                         capture_output=True, text=True, check=True).stdout)

    ITEMS = json.dumps([
        {"entry": "a", "kind": "issue", "title": "Redis SCAN", "body": "cursor bug", "last_ts": "2026-01-03", "reporters": ["a"], "tags": ["redis"], "scopes": ["search/"]},
        {"entry": "b", "kind": "caveat", "title": "CI cache", "body": "key too wide", "last_ts": "2026-01-02", "reporters": ["a", "b"], "tags": ["ci"], "scopes": []},
        {"entry": "c", "kind": "caveat", "title": "Old", "status": "obsolete", "last_ts": "2026-01-09", "reporters": ["a", "b", "c"], "tags": ["ci"]},
        {"entry": "d", "kind": "caveat", "title": "Lock", "last_ts": "2026-01-01", "reporters": ["a", "b", "c"], "tags": []}])

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_filters_narrow_the_list_and_obsolete_items_stay_out(self):
        run = lambda f: [i["entry"] for i in self.helpers(f"knFilter({self.ITEMS}, Object.assign(knDefaults(), {f}))")]
        self.assertEqual(run("{}"), ["a", "b", "d"])  # newest first; the obsolete item is left out
        self.assertEqual(run("{obsolete: true}"), ["c", "a", "b", "d"])
        self.assertEqual(run("{kind: 'caveat'}"), ["b", "d"])
        self.assertEqual(run("{tag: 'redis'}"), ["a"])
        self.assertEqual(run("{scope: 'search/'}"), ["a"])
        self.assertEqual(run("{shared: true}"), ["b", "d"])
        self.assertEqual(run("{q: 'KEY wide'}"), ["b"])  # every word, in the title, text, tags, or scope
        self.assertEqual(run("{sort: 'reporters'}"), ["d", "b", "a"])  # most reporters first, then newest

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_stats_count_the_visible_items(self):
        col = {"view": {"order": ["issue", "caveat"], "groups": {}}, "items": json.loads(self.ITEMS)}
        got = self.helpers(f"(() => {{ const s = knStats({json.dumps(col)}, knDefaults()); "
                           "return {total: s.total, reporters: s.reporters, order: s.order, kinds: [...s.kinds], tags: s.tags, scopes: s.scopes}; })()")
        self.assertEqual((got["total"], got["reporters"], got["order"]), (3, 3, ["issue", "caveat"]))
        self.assertEqual(got["kinds"], [["issue", 1], ["caveat", 2]])
        self.assertEqual(got["tags"], [["ci", 1], ["redis", 1]])
        self.assertEqual(got["scopes"], ["search/"])

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_an_active_filter_always_has_a_control(self):
        tags = [{"entry": f"e{i}", "kind": "caveat", "tags": [f"t{i:02d}"] * 1 + ["common"], "scopes": ["a/"], "reporters": ["s"], "last_ts": "1"} for i in range(25)]
        tags.append({"entry": "old", "kind": "caveat", "status": "obsolete", "tags": ["gone"], "scopes": ["old/"], "reporters": ["s"], "last_ts": "1"})
        col = {"view": {}, "items": tags}

        def run(flt):
            return self.helpers(f"(() => {{ const f = {{...knDefaults(), ...{flt}}}; const c = knControls(knStats({json.dumps(col)}, f), f); "
                                "return {kinds: c.kinds, tags: c.tags.map((t) => t.join(':')), scopes: c.scopes}; })()")
        got = run("{}")
        self.assertEqual(len(got["tags"]), 20)  # the top chips only
        self.assertEqual(got["scopes"], ["a/"])
        rare = [t for t in run("{tag: 't24'}")["tags"] if t.startswith("t24")]
        self.assertEqual(rare, ["t24:1"])  # below the top 20 but in the pool: its real count, not 0
        self.assertEqual([t for t in run("{tag: 'gone'}")["tags"] if t.startswith("gone")], ["gone:0"])  # obsolete item hidden
        self.assertEqual(run("{}")["kinds"], ["caveat"])
        self.assertEqual(run("{kind: 'decision'}")["kinds"], ["caveat", "decision"])  # no item has it, yet it can be cleared
        self.assertEqual(run("{kind: 'caveat'}")["kinds"], ["caveat"])  # listed once
        self.assertEqual(run("{scope: 'old/'}")["scopes"], ["a/", "old/"])
        self.assertEqual(run("{obsolete: true, scope: 'old/'}")["scopes"], ["a/", "old/"])  # listed once

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_a_malformed_hash_selects_nothing(self):
        js = template("knowledge.js")
        code = re.search(r"  const knEntry = .*?\n", js, re.S)[0]
        out = subprocess.run(["node", "-e", f"const location = {{ hash: '#%E0%A4%A' }};\n{code}\nconsole.log(JSON.stringify(knEntry()))"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), "")

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_filters_round_trip_through_the_address(self):
        got = self.helpers("(() => { const f = knParse('?kind=issue&tag=ci&q=a%20b&sort=reporters&shared=1'); "
                           "return [f, knSerialize(f), knSerialize(knDefaults()), knParse('?sort=nonsense').sort]; })()")
        self.assertEqual((got[0]["kind"], got[0]["tag"], got[0]["q"], got[0]["sort"], got[0]["shared"]), ("issue", "ci", "a b", "reporters", True))
        self.assertEqual(got[1], "?kind=issue&tag=ci&q=a+b&sort=reporters&shared=1")
        self.assertEqual((got[2], got[3]), ("", "recent"))  # the defaults leave the address bare

    def test_dashboard_links_to_the_page_in_both_languages(self):
        page = dashboard_html()
        self.assertIn('href="knowledge"', page)
        for key in ("kn.error", "kn.unauthorized", "btn.knowledge", "btn.knowledgeTitle", "kn.title", "kn.search", "kn.rev"):
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

    @unittest.skipUnless(shutil.which("node"), "needs Node.js")
    def test_dashboard_selects_the_session_named_by_the_hash_once(self):
        code = re.search(r"  function openHashedTab\(.*?\n  }\n", dashboard_html(), re.S)[0]
        script = """
          const calls = [];
          const location = { hash: "#session:a%20b", pathname: "/", search: "" };
          const history = { replaceState: (_s, _t, url) => { calls.push(["url", url]); location.hash = ""; } };
          const setView = (v) => calls.push(["view", v]);
          const ui = { layout: "list" };
          const selectSession = (id) => calls.push(["select", id]);
          const openPanel = (id) => calls.push(["panel", id]);
          openHashedTab(false); openHashedTab(true); openHashedTab(true);
          location.hash = "#session:%E0"; openHashedTab(true);  // malformed: selects nothing, throws nothing
          ui.layout = "grid"; location.hash = "#session:c"; openHashedTab(true);  // the grid opens the panel
          console.log(JSON.stringify(calls));
        """
        out = subprocess.run(["node", "-e", code + script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [["select", "a b"], ["url", "/"], ["url", "/"], ["panel", "c"], ["url", "/"]])


if __name__ == "__main__":
    unittest.main()
