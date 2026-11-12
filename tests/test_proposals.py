"""Tests for scripts/proposals.py: scaffolding, numbering, and the format check."""

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("proposals", ROOT / "scripts" / "proposals.py")
proposals = importlib.util.module_from_spec(spec)
sys.modules["proposals"] = proposals  # dataclasses look the module up while the class is built
spec.loader.exec_module(proposals)


def fill(path: Path, **replace: str) -> None:
    """Replace every TBD section with prose so the proposal passes the placeholder check."""
    text = path.read_text().replace("TBD", "Filled in for the test.")
    for old, new in replace.items():
        text = text.replace(old, new)
    path.write_text(text)


class ProposalsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.template = self.dir / "TEMPLATE.md"
        shutil.copy(ROOT / "proposals" / "TEMPLATE.md", self.template)

    def tearDown(self):
        self.tmp.cleanup()

    def new(self, slug, **kw):
        args = {"title": "A title", "topic": "Protocol", "author": "octocat", **kw}
        return proposals.create(slug, directory=self.dir, template=self.template, **args)

    def test_new_allocates_sequential_numbers_and_fills_metadata(self):
        first = self.new("first-idea")
        second = self.new("second-idea", status="Approved")
        self.assertEqual((first.name, second.name), ("SH-0001-first-idea.md", "SH-0002-second-idea.md"))
        p = proposals.parse(second)
        self.assertEqual((p.title, p.status, p.fields["Author"]),
                         ("A title", "Approved", "[@octocat](https://github.com/octocat)"))

    def test_fresh_scaffold_fails_until_sections_are_filled(self):
        path = self.new("idea")
        self.assertTrue(any("TBD" in e for e in proposals.lint(self.dir)))
        fill(path)
        self.assertEqual(proposals.lint(self.dir), [])

    def test_lint_catches_format_problems(self):
        fill(self.new("dup-a"))
        dup = self.dir / "SH-0001-dup-b.md"
        shutil.copy(self.dir / "SH-0001-dup-a.md", dup)
        fill(self.new("bad-status"), **{"**Proposed**": "**Maybe**"})
        fill(self.new("placeholder", author="handle"))
        fill(self.new("bad-link"), **{"Filled in for the test.\n\n## Detailed": "See [x](missing.md).\n\n## Detailed"})
        errors = "\n".join(proposals.lint(self.dir))
        self.assertIn("duplicate number SH-0001", errors)
        self.assertIn("'Status' must be one of", errors)
        self.assertIn("placeholder handle", errors)
        self.assertIn("broken relative link: missing.md", errors)

    def test_implemented_needs_pr_and_ticked_boxes(self):
        path = self.new("done", status="Implemented")
        fill(path)
        errors = "\n".join(proposals.lint(self.dir))
        self.assertIn("needs its 'Implementing PR'", errors)
        self.assertIn("every Progress box ticked", errors)
        fill(path, **{"| Implementing PR | — |": "| Implementing PR | [#7](https://github.com/o/r/pull/7) |",
                      "- [ ]": "- [x]"})
        self.assertEqual(proposals.lint(self.dir), [])

    def test_create_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            self.new("Not A Slug")
        with self.assertRaises(ValueError):
            self.new("ok", topic="Weather")

    def test_repository_proposals_pass_lint(self):
        self.assertEqual(proposals.lint(), [])


if __name__ == "__main__":
    unittest.main()
