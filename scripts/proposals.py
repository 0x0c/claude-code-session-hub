#!/usr/bin/env python3
"""Create, list, and lint Session Hub proposals (``proposals/SH-NNNN-<slug>.md``).

A proposal is a design document that we write and review before we build a change.
This script keeps the format mechanical so that reviews can focus on the argument:

    python3 scripts/proposals.py new --slug push-retry --title "Retry pushes with backoff" \
        --topic Protocol --author <github-handle>
    python3 scripts/proposals.py list [--status Approved] [--grep retry]
    python3 scripts/proposals.py lint

``new`` allocates the next free number at creation time. Two branches can allocate the
same number in parallel; ``lint`` reports the duplicate, and the branch that merges second
renumbers its proposal.
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
TEMPLATE = PROPOSALS_DIR / "TEMPLATE.md"

STATUSES = ("Proposed", "Approved", "In progress", "Implemented", "Deferred", "Rejected")
TOPICS = (
    "Protocol", "Hub server", "Dashboard", "Collections", "Hooks and skills",
    "Distribution", "Developer workflow",
)
SECTIONS = ("Introduction", "Motivation", "Detailed design", "Alternatives considered",
            "Progress", "References")
FIELDS = ("Proposal", "Author", "Status", "Topic", "Implementing PR", "Related")

FILE_RE = re.compile(r"^SH-(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
TITLE_RE = re.compile(r"^# SH-(\d{4}) — (.+)$")
HANDLE_RE = re.compile(r"^\[@([A-Za-z0-9-]+)\]\(https://github\.com/([A-Za-z0-9-]+)\)$")
PR_RE = re.compile(r"^\[#(\d+)\]\(https://github\.com/[^)]+/pull/(\d+)\)$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PLACEHOLDER_HANDLE = "handle"
NONE = "—"


@dataclass
class Proposal:
    path: Path
    number: int | None = None
    slug: str | None = None
    title: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    sections: list[str] = field(default_factory=list)
    text: str = ""

    @property
    def status(self) -> str:
        return self.fields.get("Status", "").strip("*")


def parse(path: Path) -> Proposal:
    text = path.read_text(encoding="utf-8")
    p = Proposal(path=path, text=text)
    m = FILE_RE.match(path.name)
    if m:
        p.number, p.slug = int(m.group(1)), m.group(2)
    lines = text.splitlines()
    if lines:
        t = TITLE_RE.match(lines[0])
        if t:
            p.title = t.group(2)
    in_meta = False
    for line in lines:
        if line.strip() == "<!-- SH-METADATA -->":
            in_meta = True
            continue
        if line.strip() == "<!-- /SH-METADATA -->":
            in_meta = False
            continue
        if in_meta and line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] != "Field":
                p.fields[cells[0]] = cells[1]
        if line.startswith("## "):
            p.sections.append(line[3:].strip())
    return p


def load_all(directory: Path = PROPOSALS_DIR) -> list[Proposal]:
    return [parse(f) for f in sorted(directory.glob("SH-*.md"))]


# ---- lint -----------------------------------------------------------------

def lint(directory: Path = PROPOSALS_DIR) -> list[str]:
    """Return one message per problem; an empty list means every proposal is well formed."""
    errors: list[str] = []
    proposals = load_all(directory)
    seen: dict[int, Path] = {}
    for p in proposals:
        name = p.path.name

        def err(msg: str) -> None:
            errors.append(f"{name}: {msg}")

        if p.number is None:
            err("file name must match SH-NNNN-<lowercase-slug>.md")
            continue
        if p.number in seen:
            err(f"duplicate number SH-{p.number:04d} (also {seen[p.number].name}); renumber one of them")
        seen.setdefault(p.number, p.path)
        first = p.text.splitlines()[0] if p.text else ""
        t = TITLE_RE.match(first)
        if not t:
            err("first line must be '# SH-NNNN — <Title>' (with an em dash)")
        elif int(t.group(1)) != p.number:
            err(f"title number SH-{t.group(1)} does not match the file name")

        missing = [f for f in FIELDS if f not in p.fields]
        if missing:
            err(f"metadata table is missing: {', '.join(missing)}")
            continue
        if p.fields["Proposal"] != f"SH-{p.number:04d}":
            err(f"'Proposal' must be SH-{p.number:04d}")
        author = p.fields["Author"]
        a = HANDLE_RE.match(author)
        if not a or a.group(1) != a.group(2):
            err("'Author' must be [@handle](https://github.com/handle)")
        elif a.group(1) == PLACEHOLDER_HANDLE:
            err("'Author' still holds the placeholder handle; ask the author for their GitHub handle")
        if p.status not in STATUSES:
            err(f"'Status' must be one of: {', '.join(STATUSES)} (got {p.fields['Status']!r})")
        if p.fields["Status"] != f"**{p.status}**":
            err("'Status' must be bold, e.g. **Approved**")
        if p.fields["Topic"] not in TOPICS:
            err(f"'Topic' must be one of: {', '.join(TOPICS)}")

        pr = p.fields["Implementing PR"]
        if pr != NONE:
            m = PR_RE.match(pr)
            if not m or m.group(1) != m.group(2):
                err(f"'Implementing PR' must be {NONE} or [#N](https://github.com/<owner>/<repo>/pull/N)")

        if p.sections != list(SECTIONS):
            err(f"sections must be exactly, in order: {', '.join(SECTIONS)} (got {', '.join(p.sections)})")
        if re.search(r"^TBD\s*$", p.text, re.MULTILINE):
            err("a section still says TBD; fill it before committing")

        boxes = re.findall(r"^- \[( |x)\] ", p.text, re.MULTILINE)
        if p.status == "Implemented":
            if pr == NONE:
                err("an Implemented proposal needs its 'Implementing PR'")
            if not boxes or " " in boxes:
                err("an Implemented proposal needs every Progress box ticked")

        for target in LINK_RE.findall(p.text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            local = (p.path.parent / target.split("#", 1)[0]).resolve()
            if not local.exists():
                err(f"broken relative link: {target}")
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
           directory: Path = PROPOSALS_DIR, template: Path = TEMPLATE) -> Path:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("slug must be lowercase words joined by hyphens, e.g. push-retry")
    if topic not in TOPICS:
        raise ValueError(f"topic must be one of: {', '.join(TOPICS)}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    number = next_number(directory)
    ident = f"SH-{number:04d}"
    text = (template.read_text(encoding="utf-8")
            .replace("SH-NNNN", ident).replace("<Title>", title)
            .replace("<handle>", author).replace("<Topic>", topic).replace("<Status>", status))
    path = directory / f"{ident}-{slug}.md"
    path.write_text(text, encoding="utf-8")
    return path


# ---- CLI ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proposals", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="scaffold a proposal with the next free number")
    n.add_argument("--slug", required=True)
    n.add_argument("--title", required=True)
    n.add_argument("--topic", required=True, choices=TOPICS)
    n.add_argument("--author", help="GitHub handle of the author (never guess it)")
    n.add_argument("--status", default="Proposed", choices=STATUSES)

    ls = sub.add_parser("list", help="list proposals")
    ls.add_argument("--status", choices=STATUSES)
    ls.add_argument("--grep", help="case-insensitive match on the title, topic, or full text")

    sub.add_parser("lint", help="check every proposal's format")
    args = parser.parse_args(argv)

    if args.cmd == "new":
        author = resolve_author(args.author)
        if not author:
            print("proposals: no author handle. Pass --author <github-handle>; ask the author "
                  f"rather than guessing (use --author {PLACEHOLDER_HANDLE} only when nobody can answer).",
                  file=sys.stderr)
            return 2
        try:
            path = create(args.slug, args.title, args.topic, author, args.status)
        except ValueError as e:
            print(f"proposals: {e}", file=sys.stderr)
            return 2
        print(path.relative_to(ROOT))
        return 0

    if args.cmd == "list":
        rows = []
        for p in load_all():
            if args.status and p.status != args.status:
                continue
            if args.grep and args.grep.lower() not in p.text.lower():
                continue
            rows.append(f"SH-{p.number:04d}  {p.status:<12} {p.fields.get('Topic', '-'):<18} {p.title}")
        print("\n".join(rows) if rows else "(no proposals)")
        return 0

    errors = lint()
    for e in errors:
        print(e, file=sys.stderr)
    print(f"proposals: {len(load_all())} checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
