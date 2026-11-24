"""Static checks of the dashboard page. The suite has no browser, so these cover its wiring."""

import re
import unittest
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "session_hub/templates/dashboard.html").read_text(encoding="utf-8")


def messages(lang: str) -> set[str]:
    block = re.search(rf"^    {lang}: \{{\n(.*?)^    \}},$", PAGE, re.M | re.S).group(1)
    return set(re.findall(r'"([a-z]\w*\.?[\w.]*)": "', block))


class DashboardTest(unittest.TestCase):
    def test_every_label_exists_in_both_languages(self):
        singular = {k for k in messages("en") if k.endswith("_one")}  # Japanese has no singular form
        self.assertEqual(messages("en") - singular, messages("ja"))

    def test_static_labels_are_defined(self):
        used = set(re.findall(r'data-i18n(?:-title|-aria)?="([^"]+)"', PAGE))
        self.assertLessEqual(used, messages("en"))

    def test_script_ids_exist_in_the_page(self):
        used = set(re.findall(r'\$\("(\w+)"\)', PAGE))
        self.assertLessEqual(used, set(re.findall(r'\bid="(\w+)"', PAGE)))

    def test_layout_toggle_offers_list_and_grid(self):
        self.assertEqual(re.findall(r'<button data-layout="(\w+)"', PAGE), ["list", "grid"])
        self.assertIn('localStorage.getItem("hub.layout")', PAGE)

    def test_closed_grid_panel_is_inert(self):
        self.assertIn('$("detail").inert = grid && !ui.panelOpen;', PAGE)


if __name__ == "__main__":
    unittest.main()
