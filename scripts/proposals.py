#!/usr/bin/env python3
"""Create, list, and lint Session Hub proposals.

A proposal is a design document that we write and review before we build a change. Each proposal
is a pair of files: the English original ``proposals/SH-NNNN-<slug>.md`` and its Japanese mirror
``proposals/SH-NNNN-<slug>.ja.md``. This script keeps the format mechanical so that reviews can
focus on the argument:

    python3 scripts/proposals.py new --slug push-retry --title "Retry pushes with backoff" \
        --title-ja "プッシュの再試行" --topic Protocol --author <github-handle>
    python3 scripts/proposals.py list [--status Approved] [--grep retry]
    python3 scripts/proposals.py lint

``new`` allocates the next free number at creation time. Two branches can allocate the same number
in parallel; ``lint`` reports the duplicate, and the branch that merges second renumbers its
proposal.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROPOSALS_DIR = ROOT / "proposals"

STATUSES = ("Proposed", "Approved", "In progress", "Implemented", "Deferred", "Rejected")
TOPICS = (
    "Protocol", "Hub server", "Dashboard", "Collections", "Hooks and skills",
    "Distribution", "Developer workflow",
)


@dataclass(frozen=True)
class Language:
    """The fixed vocabulary of one language's proposal file."""

    suffix: str          # "" for the English original, ".ja" for the Japanese mirror
    fields: tuple        # metadata row labels, in order
    sections: tuple      # H2 headings, in order
    switch: str          # the language-switch line, with {en} and {ja} file names


EN = Language(
    suffix="",
    fields=("Proposal", "Author", "Status", "Topic", "Implementing PR", "Related"),
    sections=("Introduction", "Motivation", "Detailed design", "Alternatives considered",
              "Progress", "References"),
    switch="**English** · [日本語]({ja})",
)
JA = Language(
    suffix=".ja",
    fields=("提案", "作者", "状態", "トピック", "実装PR", "関連"),
    sections=("はじめに", "動機", "詳細設計", "検討した代替案", "進捗", "参考資料"),
    switch="[English]({en}) · **日本語**",
)
LANGUAGES = (EN, JA)

FILE_RE = re.compile(r"^SH-(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)(\.ja)?\.md$")
TITLE_RE = re.compile(r"^# SH-(\d{4}) — (.+)$")
HANDLE_RE = re.compile(r"^\[@([A-Za-z0-9-]+)\]\(https://github\.com/([A-Za-z0-9-]+)\)$")
PR_RE = re.compile(r"^\[#(\d+)\]\(https://github\.com/[^)]+/pull/(\d+)\)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PLACEHOLDER_HANDLE = "handle"
NONE = "—"


def strip_code(text: str) -> str:
    """Drop fenced code blocks and inline code spans, whose example links are not real links."""
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.sub(r"`[^`\n]*`", "", text)


@dataclass
class Proposal:
    path: Path
    lang: Language = EN
    number: int | None = None
    slug: str | None = None
    title: str | None = None
    title_number: int | None = None
    first_line: str = ""
    rows: dict[str, str] = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)
    text: str = ""

    def value(self, index: int) -> str | None:
        """Return the metadata value at a language-independent position (0 = proposal id)."""
        return self.rows.get(self.lang.fields[index])

    @property
    def status(self) -> str:
        return (self.value(2) or "").strip("*")

    @property
    def topic(self) -> str:
        return self.value(3) or ""


def parse(path: Path) -> Proposal:
    text = path.read_text(encoding="utf-8")
    m = FILE_RE.match(path.name)
    lang = JA if (m and m.group(3)) or path.name.endswith(".ja.md") else EN
    p = Proposal(path=path, lang=lang, text=text)
    if m:
        p.number, p.slug = int(m.group(1)), m.group(2)
    lines = text.splitlines()
    p.first_line = lines[0] if lines else ""
    in_meta = False
    for line in lines:
        if p.title is None and line.startswith("# "):
            t = TITLE_RE.match(line)
            p.title = t.group(2) if t else ""
            p.title_number = int(t.group(1)) if t else None
        if line.strip() == "<!-- SH-METADATA -->":
            in_meta = True
            continue
        if line.strip() == "<!-- /SH-METADATA -->":
            in_meta = False
            continue
        if in_meta and line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in ("Field", "項目"):
                p.rows[cells[0]] = cells[1]
        if line.startswith("## "):
            p.sections.append(line[3:].strip())
    return p


def load_all(directory: Path = PROPOSALS_DIR) -> list[Proposal]:
    """Return the English originals; each one's mirror is reached through ``mirror_of``."""
    return [parse(f) for f in sorted(directory.glob("SH-*.md")) if not f.name.endswith(".ja.md")]


def mirror_path(original: Path) -> Path:
    return original.with_name(original.name[:-3] + ".ja.md")


# ---- lint -----------------------------------------------------------------

def _lint_file(p: Proposal, number: int, err) -> None:
    """Check the rules that hold for a single file in either language."""
    lang = p.lang
    en_name = f"SH-{number:04d}-{p.slug}.md"
    expected_switch = lang.switch.format(en=en_name, ja=mirror_path(Path(en_name)).name)
    if p.first_line != expected_switch:
        err(f"first line must be the language switch: {expected_switch}")
    if p.title_number is None:
        err("the first heading must be '# SH-NNNN — <Title>' (with an em dash)")
    elif p.title_number != number:
        err(f"title number SH-{p.title_number:04d} does not match the file name")

    missing = [f for f in lang.fields if f not in p.rows]
    if missing:
        err(f"metadata table is missing: {', '.join(missing)}")
        return
    if p.value(0) != f"SH-{number:04d}":
        err(f"'{lang.fields[0]}' must be SH-{number:04d}")
    a = HANDLE_RE.match(p.value(1))
    if not a or a.group(1) != a.group(2):
        err(f"'{lang.fields[1]}' must be [@handle](https://github.com/handle)")
    elif a.group(1) == PLACEHOLDER_HANDLE:
        err(f"'{lang.fields[1]}' still holds the placeholder handle; ask the author for their GitHub handle")
    if p.status not in STATUSES:
        err(f"'{lang.fields[2]}' must be one of: {', '.join(STATUSES)} (got {p.value(2)!r})")
    if p.value(2) != f"**{p.status}**":
        err(f"'{lang.fields[2]}' must be bold, e.g. **Approved**")
    if p.topic not in TOPICS:
        err(f"'{lang.fields[3]}' must be one of: {', '.join(TOPICS)}")
    pr = p.value(4)
    if pr != NONE:
        m = PR_RE.match(pr)
        if not m or m.group(1) != m.group(2):
            err(f"'{lang.fields[4]}' must be {NONE} or [#N](https://github.com/<owner>/<repo>/pull/N)")

    if p.sections != list(lang.sections):
        err(f"sections must be exactly, in order: {', '.join(lang.sections)} (got {', '.join(p.sections)})")
    if re.search(r"^TBD\s*$", p.text, re.MULTILINE):
        err("a section still says TBD; fill it before committing")

    boxes = re.findall(r"^- \[( |x)\] ", p.text, re.MULTILINE)
    if p.status == "Implemented":
        if pr == NONE:
            err(f"an Implemented proposal needs its '{lang.fields[4]}'")
        if not boxes or " " in boxes:
            err("an Implemented proposal needs every progress box ticked")

    for target in LINK_RE.findall(strip_code(p.text)):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (p.path.parent / target.split("#", 1)[0]).resolve().exists():
            err(f"broken relative link: {target}")


def lint(directory: Path = PROPOSALS_DIR) -> list[str]:
    """Return one message per problem; an empty list means every proposal is well formed."""
    errors: list[str] = []
    seen: dict[int, Path] = {}

    for path in sorted(directory.glob("SH-*.md")):
        if path.name.endswith(".ja.md") and not path.with_name(path.name[:-6] + ".md").exists():
            errors.append(f"{path.name}: Japanese mirror without an English original")
        elif not FILE_RE.match(path.name):
            errors.append(f"{path.name}: file name must match SH-NNNN-<lowercase-slug>.md (or .ja.md)")

    for p in load_all(directory):
        if p.number is None:
            continue

        def err(msg: str, name: str = p.path.name) -> None:
            errors.append(f"{name}: {msg}")

        if p.number in seen:
            err(f"duplicate number SH-{p.number:04d} (also {seen[p.number].name}); renumber one of them")
        seen.setdefault(p.number, p.path)
        _lint_file(p, p.number, err)

        ja_path = mirror_path(p.path)
        if not ja_path.exists():
            err(f"missing Japanese mirror {ja_path.name}")
            continue
        ja = parse(ja_path)
        _lint_file(ja, p.number, lambda msg: err(msg, ja_path.name))
        # The mirror must agree with the original on every metadata value.
        for i in range(len(EN.fields)):
            if p.value(i) is not None and ja.value(i) is not None and p.value(i) != ja.value(i):
                err(f"'{JA.fields[i]}' ({ja.value(i)}) differs from '{EN.fields[i]}' ({p.value(i)})",
                    ja_path.name)
    return errors


# ---- new ------------------------------------------------------------------

def resolve_author(explicit: str | None) -> str | None:
    """Return the author's GitHub handle without guessing.

    The handle comes from --author, then $GITHUB_ACTOR, then `git config github.user`.
    A missing handle is an error rather than a guess: the Author row credits a real person.
    """
    if explicit:
        return explicit.lstrip("@")
    if os.environ.get("GITHUB_ACTOR"):
        return os.environ["GITHUB_ACTOR"]
    try:
        out = subprocess.run(["git", "config", "github.user"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or None
    except OSError:
        return None


def next_number(directory: Path = PROPOSALS_DIR) -> int:
    numbers = [p.number for p in load_all(directory) if p.number is not None]
    return max(numbers, default=0) + 1


def create(slug: str, title: str, topic: str, author: str, status: str = "Proposed",
           title_ja: str | None = None, directory: Path = PROPOSALS_DIR,
           template_dir: Path = PROPOSALS_DIR) -> tuple[Path, Path]:
    """Scaffold the English original and the Japanese mirror; return both paths."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("slug must be lowercase words joined by hyphens, e.g. push-retry")
    if topic not in TOPICS:
        raise ValueError(f"topic must be one of: {', '.join(TOPICS)}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    ident = f"SH-{next_number(directory):04d}"
    paths = []
    for lang, heading in ((EN, title), (JA, title_ja or title)):
        template = template_dir / f"TEMPLATE{lang.suffix}.md"
        text = (template.read_text(encoding="utf-8")
                .replace("SH-NNNN", ident).replace("<slug>", slug).replace("<Title>", heading)
                .replace("<handle>", author).replace("<Topic>", topic).replace("<Status>", status))
        path = directory / f"{ident}-{slug}{lang.suffix}.md"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths[0], paths[1]


# ---- CLI ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proposals", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="scaffold a proposal pair with the next free number")
    n.add_argument("--slug", required=True)
    n.add_argument("--title", required=True, help="the English title")
    n.add_argument("--title-ja", help="the Japanese title (defaults to the English title)")
    n.add_argument("--topic", required=True, choices=TOPICS)
    n.add_argument("--author", help="GitHub handle of the author (never guess it)")
    n.add_argument("--status", default="Proposed", choices=STATUSES)

    ls = sub.add_parser("list", help="list proposals")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--grep", help="case-insensitive match on the full text of either language")

    sub.add_parser("lint", help="check every proposal pair's format")
    args = parser.parse_args(argv)

    if args.cmd == "new":
        author = resolve_author(args.author)
        if not author:
            print("proposals: no author handle. Pass --author <github-handle>; ask the author "
                  f"rather than guessing (use --author {PLACEHOLDER_HANDLE} only when nobody can answer).",
                  file=sys.stderr)
            return 2
        try:
            paths = create(args.slug, args.title, args.topic, author, args.status, args.title_ja)
        except ValueError as e:
            print(f"proposals: {e}", file=sys.stderr)
            return 2
        for path in paths:
            print(path.relative_to(ROOT))
        return 0

    if args.cmd == "list":
        rows = []
        for p in load_all():
            if args.status and p.status != args.status:
                continue
            ja = mirror_path(p.path)
            haystack = p.text + (ja.read_text(encoding="utf-8") if ja.exists() else "")
            if args.grep and args.grep.lower() not in haystack.lower():
                continue
            rows.append(f"SH-{p.number:04d}  {p.status:<12} {p.topic:<18} {p.title}")
        print("\n".join(rows) if rows else "(no proposals)")
        return 0

    errors = lint()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"proposals: {len(load_all())} checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
