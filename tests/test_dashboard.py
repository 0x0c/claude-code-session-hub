"""Static checks of the dashboard page. The suite has no browser, so these cover its wiring."""

import re
import unittest
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "session_hub/templates/dashboard.html").read_text(encoding="utf-8")

# Custom properties that the script sets on an element at run time
SET_BY_SCRIPT = {"glow", "glow-ms", "kc", "group-color", "header-h"}
SIZED = re.compile(r"(?<![\w-])(font|font-size|border(?:-\w+)*-radius|(?:row-|column-)?gap|(?:padding|margin)(?:-\w+)*):\s*([^;}]+)")
WEIGHT = re.compile(r"font-weight:(?!\s*(?:var\(|inherit))[^;}]+")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(")
PAINT = re.compile(r"(?<![\w-])(?:color|background(?:-color)?|border(?:-\w+)*-color|outline-color|fill|stroke):\s*([^;}]+)")
OUTLINE = re.compile(r"(?<![\w-])(?:border(?:-(?:top|right|bottom|left))?|outline):\s*([^;}]+)")
PAINT_VALUE = re.compile(r"var\(--|color-mix\(|(?:transparent|inherit|currentColor|none)\s*$")


def tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", block))


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
        self.assertRegex(PAGE, r'\$\("detail"\)\.inert\s*=\s*grid\s*&&\s*!ui\.panelOpen\b')

    def test_pull_request_link_is_limited_to_web_addresses(self):
        self.assertIn(r'/^https?:\/\//i.test(pr.url || "") ? pr.url : null', PAGE)
        self.assertRegex(PAGE, r'class: "pr", href: prUrl, target: "_blank", rel: "noopener noreferrer"')

    def test_detail_view_links_the_pull_request(self):
        self.assertRegex(PAGE, r'<a class="pr" id="tlPr" target="_blank" rel="noopener noreferrer" hidden>')
        self.assertIn("link.hidden = !prUrl;", PAGE)
        self.assertIn("const body = eventBody(e);", PAGE)
        self.assertIn('el("div", { class: "text" }, body)', PAGE)
        self.assertIn("p.url || (p.number && p.number === known.number ? known.url : null)", PAGE)
        self.assertIn("if (!prWebUrl(pr)) return text;", PAGE)
        self.assertIn('onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") e.stopPropagation(); }', PAGE)


class DesignTokenTest(unittest.TestCase):
    def setUp(self):
        style = re.search(r"<style>(.*?)</style>", PAGE, re.S)[1]
        style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        token_blocks, marker, rules = style.partition("* { box-sizing")
        self.assertTrue(marker)
        self.rules = marker + rules
        self.light, self.dark_auto, self.dark_chosen = map(tokens, re.findall(r":root[^{]*\{([^{}]*)\}", token_blocks))

    def test_rules_take_their_values_from_tokens(self):
        for prop, value in SIZED.findall(self.rules):
            # A calc() may add layout sizes, such as a column width, to the tokens
            value = re.sub(r"calc\((?=[^;}]*var\(--(?:space|radius)-)(?:[^()]|\([^()]*\))*\)", "", value)
            with self.subTest(prop=prop, value=value):
                self.assertNotRegex(value, r"\d(?:px|rem|em|pt)\b")
                if prop == "font-size":
                    self.assertRegex(value.strip(), r"^var\(--fs-[\w-]+\)$")
        for value in OUTLINE.findall(self.rules):
            with self.subTest(outline=value):
                self.assertRegex(value, r"^(?:0|none)\s*$|var\(--|\btransparent\b")
        for value in PAINT.findall(self.rules):
            with self.subTest(paint=value):
                self.assertRegex(value, r"^(?:" + PAINT_VALUE.pattern + ")")
        self.assertEqual(WEIGHT.findall(self.rules), [])
        self.assertEqual(COLOR.findall(self.rules), [])

    def test_every_used_property_is_defined(self):
        used = set(re.findall(r"var\(--([\w-]+)", self.rules))
        self.assertEqual(used - set(self.light) - SET_BY_SCRIPT, set())

    def test_every_status_group_has_a_fill(self):
        groups = set(re.findall(r'\bstatus\("(\w+)"\)', PAGE))
        self.assertLessEqual({"action", "active", "done"}, groups)
        self.assertEqual({f"g-{g}" for g in groups} - set(self.light), set())

    def test_both_dark_blocks_agree(self):
        self.assertTrue(self.dark_auto)
        self.assertEqual(self.dark_auto, self.dark_chosen)
        self.assertEqual(set(self.dark_auto) - set(self.light), set())


if __name__ == "__main__":
    unittest.main()
