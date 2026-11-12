"""Tests for scripts/proposals.py and scripts/check_docs.py."""

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up while a class is built
    spec.loader.exec_module(module)
    return module


proposals = load("proposals")
check_docs = load("check_docs")


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
        for name in ("TEMPLATE.md", "TEMPLATE.ja.md"):
            shutil.copy(ROOT / "proposals" / name, self.dir / name)

    def tearDown(self):
        self.tmp.cleanup()

    def new(self, slug, **kw):
        args = {"title": "A title", "topic": "Protocol", "author": "octocat", **kw}
        en, ja = proposals.create(slug, directory=self.dir, template_dir=self.dir, **args)
        return en, ja

    def fill_pair(self, slug, **kw):
        en, ja = self.new(slug, **kw)
        fill(en)
        fill(ja)
        return en, ja

    def test_new_creates_a_numbered_pair_with_matching_metadata(self):
        self.new("first-idea")
        en, ja = self.new("second-idea", status="Approved", title_ja="二つ目の案")
        self.assertEqual((en.name, ja.name), ("SH-0002-second-idea.md", "SH-0002-second-idea.ja.md"))
        p, q = proposals.parse(en), proposals.parse(ja)
        self.assertEqual((p.title, p.status, p.value(1)),
                         ("A title", "Approved", "[@octocat](https://github.com/octocat)"))
        self.assertEqual((q.title, q.status, q.lang), ("二つ目の案", "Approved", proposals.JA))

    def test_fresh_scaffold_fails_until_both_files_are_filled(self):
        en, ja = self.new("idea")
        self.assertTrue(any("TBD" in e for e in proposals.lint(self.dir)))
        fill(en)
        self.assertTrue(any(e.startswith(ja.name) and "TBD" in e for e in proposals.lint(self.dir)))
        fill(ja)
        self.assertEqual(proposals.lint(self.dir), [])

    def test_lint_catches_format_problems(self):
        self.fill_pair("dup-a")
        for suffix in ("", ".ja"):
            shutil.copy(self.dir / f"SH-0001-dup-a{suffix}.md", self.dir / f"SH-0001-dup-b{suffix}.md")
        en, _ = self.fill_pair("bad-status")
        fill(en, **{"**Proposed**": "**Maybe**"})
        self.fill_pair("placeholder", author="handle")
        en, _ = self.fill_pair("bad-link")
        fill(en, **{"Filled in for the test.\n\n## Detailed": "See [x](missing.md).\n\n## Detailed"})
        errors = "\n".join(proposals.lint(self.dir))
        self.assertIn("duplicate number SH-0001", errors)
        self.assertIn("must be one of", errors)
        self.assertIn("placeholder handle", errors)
        self.assertIn("broken relative link: missing.md", errors)
        self.assertIn("differs from 'Status'", errors)  # the mirror still says Proposed
        self.assertIn("first line must be the language switch", errors)  # dup-b links to dup-a

    def test_mirror_must_exist_and_agree(self):
        en, ja = self.fill_pair("pair")
        ja.unlink()
        self.assertIn("missing Japanese mirror", "\n".join(proposals.lint(self.dir)))
        en.unlink()
        (self.dir / "SH-0009-orphan.ja.md").write_text("x")
        self.assertIn("without an English original", "\n".join(proposals.lint(self.dir)))

    def test_implemented_needs_pr_and_ticked_boxes(self):
        en, ja = self.fill_pair("done", status="Implemented")
        errors = "\n".join(proposals.lint(self.dir))
        self.assertIn("needs its 'Implementing PR'", errors)
        self.assertIn("needs its '実装PR'", errors)
        self.assertIn("every progress box ticked", errors)
        link = "[#7](https://github.com/o/r/pull/7)"
        fill(en, **{"| Implementing PR | — |": f"| Implementing PR | {link} |", "- [ ]": "- [x]"})
        fill(ja, **{"| 実装PR | — |": f"| 実装PR | {link} |", "- [ ]": "- [x]"})
        self.assertEqual(proposals.lint(self.dir), [])

    def test_create_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            self.new("Not A Slug")
        with self.assertRaises(ValueError):
            self.new("ok", topic="Weather")


class CheckDocsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        (self.root / rel).write_text(text)

    def test_a_matching_pair_passes(self):
        self.write("docs/GUIDE.md", "**English** · [日本語](GUIDE.ja.md)\n\n# Guide\n\n## Steps\n")
        self.write("docs/GUIDE.ja.md", "[English](GUIDE.md) · **日本語**\n\n# ガイド\n\n## 手順\n")
        self.assertEqual(check_docs.check(self.root), [])

    def test_problems_are_reported(self):
        self.write("docs/GUIDE.md", "# Guide\n\n## Steps\n\n```\nx\n```\n[a](nope.md)\n")
        self.write("docs/GUIDE.ja.md", "[English](GUIDE.md) · **日本語**\n\n# ガイド\n")
        self.write("docs/ORPHAN.ja.md", "x")
        self.write("docs/ALONE.md", "**English** · [日本語](ALONE.ja.md)\n")
        errors = "\n".join(check_docs.check(self.root))
        self.assertIn("docs/GUIDE.md: first line must be", errors)
        self.assertIn("heading structure differs", errors)
        self.assertIn("number of code blocks differs", errors)
        self.assertIn("broken relative link: nope.md", errors)
        self.assertIn("ORPHAN.ja.md: Japanese mirror without an English original", errors)
        self.assertIn("ALONE.md: missing Japanese mirror", errors)


class RepositoryTest(unittest.TestCase):
    def test_repository_proposals_pass_lint(self):
        self.assertEqual(proposals.lint(), [])


if __name__ == "__main__":
    unittest.main()
