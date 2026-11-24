"""The link to the design system page, whose address comes from HUB_DESIGN_SYSTEM_URL."""

import argparse
import contextlib
import io
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from session_hub import cli
from session_hub.guide import guide_html
from session_hub.playbook import playbook_html, template
from session_hub.server import dashboard_html, design_system_url, make_server, with_design_system
from session_hub.store import EventStore

URL = "https://example.com/design-system"


def configured(value):
    return mock.patch.dict(os.environ, {"HUB_DESIGN_SYSTEM_URL": value})


class DesignSystemLinkTest(unittest.TestCase):
    def test_hub_pages_carry_the_address(self):
        with tempfile.TemporaryDirectory() as tmp, configured(URL):
            server, hub = make_server(EventStore(Path(tmp) / "store"), port=0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                for path in ("/", "/playbook", "/guide"):
                    with self.subTest(path=path), urllib.request.urlopen(
                            f"http://127.0.0.1:{server.server_address[1]}{path}", timeout=5) as res:
                        self.assertIn(f'const DESIGN_SYSTEM_URL = "{URL}";', res.read().decode("utf-8"))
            finally:
                hub.stop()
                server.shutdown()
                server.server_close()

    def test_pages_have_no_address_when_it_is_not_configured(self):
        with configured(""):
            for html in (with_design_system(dashboard_html()), playbook_html(), guide_html()):
                self.assertIn("const DESIGN_SYSTEM_URL = null;", html)

    def test_only_web_addresses_are_accepted(self):
        for value in ("javascript:alert(1)", "file:///etc/passwd", "example.com", "https://", "http://["):
            with self.subTest(value=value), configured(value):
                self.assertIsNone(design_system_url())

    def test_address_cannot_end_the_script(self):
        with configured(URL + "</script>"):
            self.assertNotIn(URL + "</script>", with_design_system(dashboard_html()))

    def test_exported_file_does_not_carry_the_address(self):
        with tempfile.TemporaryDirectory() as tmp, configured(URL):
            out = Path(tmp) / "out.html"
            args = argparse.Namespace(out=str(out))
            with mock.patch.object(cli, "_snap", return_value={}), contextlib.redirect_stdout(io.StringIO()):
                cli.cmd_export(args)
            self.assertNotIn(URL, out.read_text(encoding="utf-8"))

    def test_header_and_playbook_menu_hold_the_link(self):
        self.assertIn('id="designSystemLink"', dashboard_html().split("</header>")[0])
        self.assertIn("href: DESIGN_SYSTEM_URL", template("playbook.js"))


if __name__ == "__main__":
    unittest.main()
