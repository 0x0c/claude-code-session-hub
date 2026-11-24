**English** · [日本語](SH-0004-proposal-folders.ja.md)

# SH-0004 — Give each proposal its own folder

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0004 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Developer workflow |
| Implementing PR | [#22](https://github.com/0x0c/claude-code-session-hub/pull/22) |
| Related | [SH-0001](../SH-0001-merge-time-numbering/SH-0001-merge-time-numbering.md) |
<!-- /SH-METADATA -->

## Introduction

Each proposal gets its own folder, `proposals/SH-NNNN-<slug>/`. The folder holds the English original,
the Japanese mirror, and any supporting files. The scripts create, check, and number folders instead
of loose pairs of files.

## Motivation

Today every proposal adds two files directly under `proposals/`, next to the README and the
templates. The listing grows twice as fast as the proposals do, and a figure that belongs to one
proposal has no place of its own.

Once the change ships, `proposals/` shows one entry per proposal. A supporting file placed in a
proposal's folder follows the folder when the proposal gets its number.

## Detailed design

### Layout

```text
proposals/
  README.md, README.ja.md, TEMPLATE.md, TEMPLATE.ja.md
  SH-0001-merge-time-numbering/
    SH-0001-merge-time-numbering.md
    SH-0001-merge-time-numbering.ja.md
```

The folder and both files share the name `SH-NNNN-<slug>`. The language-switch line stays as it was.
A link to another proposal becomes `../SH-NNNN-<slug>/SH-NNNN-<slug>.md`, and a link to the
repository root gains one `../`.

### The script

- `new` creates the folder and the pair inside it, and refuses a slug whose placeholder folder exists.
- `lint` reports a proposal file directly under `proposals/`, a malformed folder name, a folder
  without its English original, and an `SH-*.md` file whose name differs from its folder's name.
- `allocate` renames the folder with `git mv`, then renames both files in it. It rewrites links to the
  placeholder name in every Markdown file of every proposal folder.

### Migration

The three existing proposals move into folders, and every link to them is updated. A branch that still
adds a loose pair must move the pair into a folder. Until the move, `lint` fails, and after such a
branch merges, `guard` blocks the numbering of every proposal.

## Alternatives considered

- **One folder per status.** A proposal would move at each status change, and every link to the
  proposal would break. The `Status` row already records the status.
- **Short file names, such as `en.md` and `ja.md`.** The short form drops the repetition, but editor
  tabs and search results would no longer say which proposal a file belongs to.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (proposals/README.md, AGENTS.md, skills)

## References

- [`scripts/proposals.py`](../../scripts/proposals.py) — `new`, `lint`, and `allocate`.
- [`proposals/README.md`](../README.md) — the format of a proposal.
- [SH-0001](../SH-0001-merge-time-numbering/SH-0001-merge-time-numbering.md) — merge-time numbering.
