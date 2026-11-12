#!/usr/bin/env python3
"""Check that every bilingual page has its Japanese mirror and that the pair stays in step.

A bilingual page is an English original ``<name>.md`` with a Japanese mirror ``<name>.ja.md`` next
to it. For every pair, this script checks that:

- the mirror exists, and no mirror exists without an original;
- the first line of each file is the language switch that links the other file;
- both files have the same heading structure (the same number of headings at each level, in order);
- both files have the same number of fenced code blocks;
- every relative link in either file resolves.

Proposals (``proposals/SH-*.md``) follow the same rules, checked by ``scripts/proposals.py lint``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The user-facing pages that must be bilingual. Proposals are checked by scripts/proposals.py.
BILINGUAL = ["README.md", "AGENTS.md", "proposals/README.md", "docs/*.md"]

EN_SWITCH = "**English** · [日本語]({ja})"
JA_SWITCH = "[English]({en}) · **日本語**"
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"^```", re.MULTILINE)


def strip_code(text: str) -> str:
    """Drop fenced code blocks and inline code spans, whose example links are not real links."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


def originals(root: Path = ROOT) -> list[Path]:
    found: list[Path] = []
    for pattern in BILINGUAL:
        found.extend(p for p in sorted(root.glob(pattern)) if not p.name.endswith(".ja.md"))
    return found


def headings(text: str) -> list[int]:
    """Return the level of every Markdown heading outside fenced code blocks."""
    levels, in_code = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code:
            m = re.match(r"^(#{1,6}) ", line)
            if m:
                levels.append(len(m.group(1)))
    return levels


def broken_links(path: Path, text: str) -> list[str]:
    out = []
    for target in LINK_RE.findall(strip_code(text)):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (path.parent / target.split("#", 1)[0]).resolve().exists():
            out.append(target)
    return out


def check(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for en in originals(root):
        ja = en.with_name(en.name[:-3] + ".ja.md")
        rel = en.relative_to(root)
        if not ja.exists():
            errors.append(f"{rel}: missing Japanese mirror {ja.name}")
            continue
        en_text, ja_text = en.read_text(encoding="utf-8"), ja.read_text(encoding="utf-8")
        if en_text.splitlines()[:1] != [EN_SWITCH.format(ja=ja.name)]:
            errors.append(f"{rel}: first line must be {EN_SWITCH.format(ja=ja.name)}")
        if ja_text.splitlines()[:1] != [JA_SWITCH.format(en=en.name)]:
            errors.append(f"{ja.relative_to(root)}: first line must be {JA_SWITCH.format(en=en.name)}")
        if headings(en_text) != headings(ja_text):
            errors.append(f"{ja.relative_to(root)}: heading structure differs from {en.name} "
                          f"({len(headings(ja_text))} vs {len(headings(en_text))} headings)")
        if len(FENCE_RE.findall(en_text)) != len(FENCE_RE.findall(ja_text)):
            errors.append(f"{ja.relative_to(root)}: number of code blocks differs from {en.name}")
        for path, text in ((en, en_text), (ja, ja_text)):
            for target in broken_links(path, text):
                errors.append(f"{path.relative_to(root)}: broken relative link: {target}")

    for pattern in BILINGUAL:
        for ja in sorted(root.glob(pattern.replace("*.md", "*.ja.md") if "*" in pattern
                                   else pattern[:-3] + ".ja.md")):
            if not ja.with_name(ja.name[:-6] + ".md").exists():
                errors.append(f"{ja.relative_to(root)}: Japanese mirror without an English original")
    return errors


def main() -> int:
    errors = check()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"docs: {len(originals())} bilingual page(s) checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
