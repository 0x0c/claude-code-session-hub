import re
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "session_hub" / "templates" / "dashboard.html"

# Custom properties that the script sets on an element at run time
SET_BY_SCRIPT = {"glow", "glow-ms", "kc", "group-color"}
SIZED = re.compile(r"(?<![\w-])(font|font-size|border(?:-\w+)*-radius|(?:row-|column-)?gap|(?:padding|margin)(?:-\w+)*):\s*([^;}]+)")
WEIGHT = re.compile(r"font-weight:(?!\s*(?:var\(|inherit))[^;}]+")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(")
PAINT = re.compile(r"(?<![\w-])(?:color|background|background-color|border-color):\s*([^;}]+)")
PAINT_VALUE = re.compile(r"var\(--|color-mix\(|(?:transparent|inherit|currentColor|none)\s*$")


def tokens(block):
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", block))


class DesignTokenTest(unittest.TestCase):
    def setUp(self):
        style = re.search(r"<style>(.*?)</style>", PAGE.read_text(encoding="utf-8"), re.S)[1]
        style = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        token_blocks, marker, rules = style.partition("* { box-sizing")
        self.assertTrue(marker)
        self.rules = marker + rules
        self.light, self.dark_auto, self.dark_chosen = map(tokens, re.findall(r":root[^{]*\{([^{}]*)\}", token_blocks))

    def test_rules_take_their_values_from_tokens(self):
        for prop, value in SIZED.findall(self.rules):
            # A calc() may add layout sizes, such as a column width, to the tokens
            value = re.sub(r"calc\((?=[^;}]*var\(--space-)(?:[^()]|\([^()]*\))*\)", "", value)
            with self.subTest(prop=prop, value=value):
                self.assertNotRegex(value, r"\d(?:px|rem|em|pt)\b")
                if prop == "font-size":
                    self.assertRegex(value.strip(), r"^var\(--fs-[\w-]+\)$")
        for value in PAINT.findall(self.rules):
            with self.subTest(paint=value):
                self.assertRegex(value, r"^(?:" + PAINT_VALUE.pattern + ")")
        self.assertEqual(WEIGHT.findall(self.rules), [])
        self.assertEqual(COLOR.findall(self.rules), [])

    def test_every_used_property_is_defined(self):
        used = set(re.findall(r"var\(--([\w-]+)", self.rules))
        self.assertEqual(used - set(self.light) - SET_BY_SCRIPT, set())

    def test_both_dark_blocks_agree(self):
        self.assertTrue(self.dark_auto)
        self.assertEqual(self.dark_auto, self.dark_chosen)
        self.assertEqual(set(self.dark_auto) - set(self.light), set())


if __name__ == "__main__":
    unittest.main()
