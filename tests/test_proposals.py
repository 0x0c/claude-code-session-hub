"""Tests for scripts/proposals.py and scripts/check_docs.py."""

import importlib.util
import shutil
import subprocess
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
acronyms = load("acronyms")


def fill(path: Path, **replace: str) -> None:
    """Replace every TBD section with prose so the proposal passes the placeholder check."""
    text = path.read_text().replace("TBD", "Filled in for the test.")
    for old, new in replace.items():
        text = text.replace(old, new)
    path.write_text(text)


def number(en: Path, slug: str, ident: str) -> Path:
    """Give a placeholder pair a number by hand, as allocate() would, and return the English path."""
    for src in (en, proposals.mirror_path(en)):
        dst = src.with_name(src.name.replace(proposals.PLACEHOLDER, ident))
        dst.write_text(proposals._renumber_text(src.read_text(), slug, ident))
        src.unlink()
    return en.with_name(en.name.replace(proposals.PLACEHOLDER, ident))


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

    def test_new_creates_a_placeholder_pair_with_matching_metadata(self):
        self.new("first-idea")
        en, ja = self.new("second-idea", status="Approved", title_ja="二つ目の案")
        self.assertEqual((en.name, ja.name), ("SH-XXXX-second-idea.md", "SH-XXXX-second-idea.ja.md"))
        p, q = proposals.parse(en), proposals.parse(ja)
        self.assertEqual((p.ident, p.number, p.value(0)), ("SH-XXXX", None, "SH-XXXX"))
        self.assertEqual((p.title, p.status, p.value(1)),
                         ("A title", "Approved", "[@octocat](https://github.com/octocat)"))
        with self.assertRaises(ValueError):
            self.new("second-idea")  # The same slug cannot have two placeholder pairs
        self.assertEqual((q.title, q.status, q.lang), ("二つ目の案", "Approved", proposals.JA))

    def test_fresh_scaffold_fails_until_both_files_are_filled(self):
        en, ja = self.new("idea")
        self.assertTrue(any("TBD" in e for e in proposals.lint(self.dir)))
        fill(en)
        self.assertTrue(any(e.startswith(ja.name) and "TBD" in e for e in proposals.lint(self.dir)))
        fill(ja)
        self.assertEqual(proposals.lint(self.dir), [])

    def test_lint_catches_format_problems(self):
        en, _ = self.fill_pair("dup-a")
        number(en, "dup-a", "SH-0001")
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
        (self.dir / "SH-XXXX-orphan.ja.md").write_text("x")
        self.assertIn("SH-XXXX-orphan.ja.md: Japanese mirror without", "\n".join(proposals.lint(self.dir)))
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


class AllocateTest(unittest.TestCase):
    """allocate() numbers placeholders inside a real Git repository, as the workflow does on main."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dir = self.root / "proposals"
        self.dir.mkdir()
        for name in ("TEMPLATE.md", "TEMPLATE.ja.md"):
            shutil.copy(ROOT / "proposals" / name, self.dir / name)
        self.git("init", "-q")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.x", *args],
                              cwd=self.root, check=True, capture_output=True, text=True).stdout

    def pair(self, slug, extra=""):
        en, ja = proposals.create(slug, "A title", "Protocol", "octocat", directory=self.dir,
                                  template_dir=self.dir)
        fill(en, **{"Filled in for the test.\n\n## Motivation": f"Placeholder ids look like SH-XXXX.{extra}\n\n## Motivation"})
        fill(ja)
        return en

    def test_allocates_in_slug_order_above_every_used_number(self):
        number(self.pair("taken"), "taken", "SH-0003")
        self.pair("beta")
        self.pair("alpha", extra=" See [beta](SH-XXXX-beta.md).")
        self.git("add", "-A")
        self.git("commit", "-qm", "seed")

        self.assertEqual(proposals.allocate(self.dir, ref="HEAD"), [("alpha", "SH-0004"), ("beta", "SH-0005")])
        self.assertEqual(sorted(p.name for p in self.dir.glob("SH-*.md")), [
            "SH-0003-taken.ja.md", "SH-0003-taken.md", "SH-0004-alpha.ja.md", "SH-0004-alpha.md",
            "SH-0005-beta.ja.md", "SH-0005-beta.md"])
        alpha = (self.dir / "SH-0004-alpha.md").read_text()
        self.assertTrue(alpha.startswith("**English** · [日本語](SH-0004-alpha.ja.md)"))
        self.assertIn("# SH-0004 — A title", alpha)
        self.assertIn("| Proposal | SH-0004 |", alpha)
        self.assertIn("[beta](SH-0005-beta.md)", alpha)  # A link to another new proposal follows it
        self.assertIn("look like SH-XXXX.", alpha)  # Prose about the placeholder stays as written
        self.assertIn("| 提案 | SH-0004 |", (self.dir / "SH-0004-alpha.ja.md").read_text())
        self.assertEqual(proposals.lint(self.dir), [])
        self.assertIn("proposals/SH-XXXX-alpha.md -> proposals/SH-0004-alpha.md", self.git("status", "--short"))
        self.assertEqual(proposals.allocate(self.dir, ref="HEAD"), [])  # A second run is a no-op

    def test_a_slug_that_extends_another_slug_keeps_its_own_links(self):
        self.pair("beta", extra=" See [two](SH-XXXX-beta-two.md).")
        self.pair("beta-two", extra=" See [one](SH-XXXX-beta.md).")
        self.git("add", "-A")
        self.assertEqual(proposals.allocate(self.dir, ref="HEAD"), [("beta", "SH-0001"), ("beta-two", "SH-0002")])
        self.assertEqual(proposals.lint(self.dir), [])
        self.assertIn("[two](SH-0002-beta-two.md)", (self.dir / "SH-0001-beta.md").read_text())

    def test_skips_numbers_used_on_the_ref(self):
        number(self.pair("merged"), "merged", "SH-0007")
        self.git("add", "-A")
        self.git("commit", "-qm", "main")
        for path in self.dir.glob("SH-0007-*"):  # This checkout lags behind main
            path.unlink()
        self.pair("late")
        self.git("add", "-A")
        self.assertEqual(proposals.allocate(self.dir, ref="HEAD"), [("late", "SH-0008")])

    def test_guard_confines_the_commit_to_proposals(self):
        self.assertEqual(proposals.guard_problems(["proposals/SH-0001-a.md"], self.dir), [])
        self.assertEqual(proposals.guard_problems(["proposals-notes.md", "README.md"], self.dir),
                         ["outside proposals/: proposals-notes.md", "outside proposals/: README.md"])

    def test_links_to_a_placeholder_outside_proposals_are_reported(self):
        (self.root / "README.md").write_text("See [it](proposals/SH-XXXX-alpha.md). The id SH-XXXX is fine.\n")
        (self.root / "OK.md").write_text("Placeholders look like `proposals/SH-XXXX-alpha.md`.\n")
        (self.dir / "README.md").write_text("See [x](SH-XXXX-alpha.md).\n")
        self.git("add", "-A")
        problems = proposals.placeholder_links(self.root)
        self.assertEqual([x.split(":")[0] for x in problems], ["README.md", "proposals/README.md"])


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


class AcronymsTest(unittest.TestCase):
    def check(self, name, text):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / name
            path.write_text(text)
            acronyms.ROOT = Path(d)
            try:
                return acronyms.check_file(path)
            finally:
                acronyms.ROOT = ROOT

    def test_first_use_must_be_expanded(self):
        self.assertEqual(self.check("a.md", "The hub streams Server-Sent Events (SSE). SSE is cheap.\n"), [])
        errors = self.check("b.md", "The hub streams SSE to the browser.\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("Server-Sent Events (SSE)", errors[0])

    def test_japanese_parentheses_and_plurals(self):
        self.assertEqual(self.check("a.ja.md", "プルリクエスト（PR）を開きます。次のPRも同じです。\n"), [])
        self.assertEqual(self.check("b.md", "Open two pull requests (PRs). Each PR runs CI.\n")[0].split(": ", 1)[1],
                         "spell out CI on first use: continuous integration (CI)")

    def test_code_links_and_headings_do_not_count(self):
        text = "# The SSE stream\n\nRun `SSE` and see [the docs](https://e.x/SSE).\n\n```\nSSE\n```\n"
        self.assertEqual(self.check("a.md", text), [])


class RepositoryTest(unittest.TestCase):
    def test_repository_proposals_pass_lint(self):
        self.assertEqual(proposals.lint(), [])


if __name__ == "__main__":
    unittest.main()
