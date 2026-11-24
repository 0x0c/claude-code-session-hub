"""Checks on the dashboard's split layout that need no browser."""
import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "session_hub" / "templates" / "dashboard.html"


class SplitLayoutTest(unittest.TestCase):
    def setUp(self):
        self.page = PAGE.read_text(encoding="utf-8")

    def test_script_and_stylesheet_agree_on_the_split_query(self):
        query = re.search(r'const SPLIT = matchMedia\("([^"]+)"\)', self.page).group(1)
        self.assertIn("@media " + query + " {", self.page)

    def test_each_panel_has_its_own_scroll_area(self):
        for name in ("sessions", "detail"):
            self.assertRegex(self.page, r'id="%s" class="scroll"' % name)


if __name__ == "__main__":
    unittest.main()
