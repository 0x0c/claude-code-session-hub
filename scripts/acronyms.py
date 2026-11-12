#!/usr/bin/env python3
"""Check that every document spells out each acronym on its first use.

The first time a document uses an acronym in its prose, the acronym must appear in parentheses
right after the full term: "Server-Sent Events (SSE)" in English, "Server-Sent Events（SSE）" in
Japanese. Later uses may stand alone. Code, links, headings, front matter, and the proposal
metadata table do not count as prose.

    python3 scripts/acronyms.py            # check every tracked Markdown file
    python3 scripts/acronyms.py FILE...    # check the given files
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each acronym with its expansion in English and in Japanese. A self-referential name such as YAML
# ("YAML Ain't Markup Language") cannot be spelled out without itself, so it is not listed.
ACRONYMS: dict[str, tuple[str, str]] = {
    "API": ("application programming interface", "アプリケーションプログラミングインターフェース"),
    "APM": ("Agent Package Manager", "Agent Package Manager"),
    "ASCII": ("American Standard Code for Information Interchange", "American Standard Code for Information Interchange"),
    "CI": ("continuous integration", "継続的インテグレーション"),
    "CLI": ("command-line interface", "コマンドラインインターフェース"),
    "CSS": ("Cascading Style Sheets", "Cascading Style Sheets"),
    "DOM": ("Document Object Model", "Document Object Model"),
    "H2": ("second-level heading", "第2レベルの見出し"),
    "HTML": ("HyperText Markup Language", "HyperText Markup Language"),
    "HTTP": ("Hypertext Transfer Protocol", "Hypertext Transfer Protocol"),
    "ID": ("identifier", "識別子"),
    "JSON": ("JavaScript Object Notation", "JavaScript Object Notation"),
    "JSONL": ("JSON Lines", "JSON Lines"),
    "LLM": ("large language model", "大規模言語モデル"),
    "MCP": ("Model Context Protocol", "Model Context Protocol"),
    "PC": ("personal computer", "パーソナルコンピューター"),
    "PR": ("pull request", "プルリクエスト"),
    "SSE": ("Server-Sent Events", "Server-Sent Events"),
    "UI": ("user interface", "ユーザーインターフェース"),
    "URL": ("Uniform Resource Locator", "Uniform Resource Locator"),
    "UUID": ("universally unique identifier", "汎用一意識別子"),
}
SKIP = ("proposals/TEMPLATE.md", "proposals/TEMPLATE.ja.md")
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_/.\-])(" + "|".join(sorted(ACRONYMS, key=len, reverse=True))
                      + r")(s?)(?![A-Za-z0-9_])")


def prose(text: str) -> str:
    """Blank out everything that is not prose, keeping offsets so positions stay meaningful."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    text = re.sub(r"\A---\n.*?\n---\n", blank, text, flags=re.S)
    text = re.sub(r"<!-- SH-METADATA -->.*?<!-- /SH-METADATA -->", blank, text, flags=re.S)
    text = re.sub(r"^```.*?^```", blank, text, flags=re.S | re.M)
    text = re.sub(r"`[^`\n]*`", blank, text)
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    text = re.sub(r"\]\([^)]*\)", blank, text)
    text = re.sub(r"https?://\S+", blank, text)
    text = re.sub(r"^#{1,6} .*$", blank, text, flags=re.M)
    return text


def first_uses(text: str) -> dict[str, re.Match]:
    found: dict[str, re.Match] = {}
    for m in TOKEN_RE.finditer(prose(text)):
        found.setdefault(m.group(1), m)
    return found


def is_expanded(text: str, m: re.Match) -> bool:
    before, after = text[:m.start()], text[m.end():]
    return before.endswith(("(", "（")) and after.startswith((")", "）"))


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = []
    ja = path.name.endswith(".ja.md")
    for acr, m in sorted(first_uses(text).items(), key=lambda kv: kv[1].start()):
        if not is_expanded(text, m):
            line = text.count("\n", 0, m.start()) + 1
            term = ACRONYMS[acr][1 if ja else 0]
            form = f"{term}（{acr}）" if ja else f"{term} ({acr})"
            errors.append(f"{path.relative_to(ROOT)}:{line}: spell out {acr} on first use: {form}")
    return errors


def tracked_markdown() -> list[Path]:
    """Tracked Markdown files plus new ones that are not ignored, so a fresh proposal is checked too."""
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return [ROOT / f for f in sorted(set(out.split())) if f not in SKIP and (ROOT / f).exists()]


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv] or tracked_markdown()
    errors = [e for f in files for e in check_file(f)]
    for e in errors:
        print(e, file=sys.stderr)
    print(f"acronyms: {len(files)} file(s) checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
