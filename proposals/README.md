# Proposals

A proposal is a short design document that argues for one change to Session Hub before we build
it. Every non-trivial change starts as a proposal under this directory. The proposal records the
problem, the design we chose, and the alternatives we rejected, so a later reader can tell why the
code looks the way it does.

## The lifecycle of a proposal

Each proposal moves through a fixed set of statuses. The `Status` row of its metadata table records
the current one.

| Status | Meaning | Who moves it here |
|---|---|---|
| Proposed | The author wrote the proposal and asks for review. | The author, on creation |
| Approved | The maintainer accepted the design; anyone may build it. | The maintainer, on review |
| In progress | Someone is building it on a branch. | The implementer, when work starts |
| Implemented | The change has landed; the `Implementing PR` row links it. | The implementer, in the implementing PR |
| Deferred | The design is sound, but we chose not to build it now. | The maintainer |
| Rejected | We decided against the change; the proposal stays as a record. | The maintainer |

Three skills under [`.claude/skills/`](../.claude/skills/) drive this lifecycle:

- [`ideation`](../.claude/skills/ideation/SKILL.md) turns a rough idea into a proposal at
  `Proposed` and never touches product code.
- [`implement-proposal`](../.claude/skills/implement-proposal/SKILL.md) builds an `Approved`
  proposal and moves it to `Implemented`.
- [`propose-and-build`](../.claude/skills/propose-and-build/SKILL.md) writes a small, settled
  proposal and its implementation together, in one pull request.

## Add a proposal

Scaffold the file with the script rather than by hand. The script allocates the next free number
and fills the metadata table from [`TEMPLATE.md`](TEMPLATE.md).

```bash
python3 scripts/proposals.py new --slug push-retry --title "Retry pushes with backoff" \
  --topic Protocol --author <github-handle>
```

The command prints the path of the new file, for example `proposals/SH-0002-push-retry.md`. Then
fill every `TBD` section under the [`document-writing`](../.claude/skills/document-writing/SKILL.md)
and [`english-document-writing`](../.claude/skills/english-document-writing/SKILL.md) skills.

Two branches can allocate the same number in parallel. The format check reports the duplicate, and
the branch that merges second renumbers its proposal.

## The format of a proposal

A proposal is one Markdown file named `SH-NNNN-<slug>.md`, written in English. The format check
(`python3 scripts/proposals.py lint`) enforces the rules below.

- **Title.** The first line is `# SH-NNNN — <Title>`, with an em dash.
- **Metadata table.** The table between `<!-- SH-METADATA -->` and `<!-- /SH-METADATA -->` holds
  six rows in this order: `Proposal`, `Author`, `Status`, `Topic`, `Implementing PR`, and `Related`.
  - `Author` is the author's GitHub handle as a link. Never guess a handle; ask the author.
  - `Status` is one of the six statuses above, in bold.
  - `Topic` is one of: Protocol, Hub server, Dashboard, Collections, Hooks and skills,
    Distribution, or Developer workflow.
  - `Implementing PR` is `—` until a pull request implements the proposal, then a link to it.
  - `Related` is `—` or links to other proposals.
- **Sections.** Six H2 sections appear exactly in this order:
  1. *Introduction* states the change and its contribution in one or two paragraphs.
  2. *Motivation* states the problem, why it matters, and one observable difference the change
     will make, so a later reader can check whether the change worked.
  3. *Detailed design* describes the change precisely enough to build and review it.
  4. *Alternatives considered* lists the designs we rejected, each with its reason.
  5. *Progress* is a checklist; an `Implemented` proposal has every box ticked.
  6. *References* links the code, documents, and prior proposals the proposal builds on.
- **No placeholders.** No section may still say `TBD` when the proposal is committed.

## List proposals

```bash
python3 scripts/proposals.py list
python3 scripts/proposals.py list --status Approved
python3 scripts/proposals.py list --grep dashboard
```

## Unsorted ideas

Add an unformed idea here as one bullet. Promote it to a numbered proposal once its scope is clear.

- **English product strings.** The dashboard labels, the CLI messages, and the text that the hooks
  inject are Japanese. Switching them to English, or making them selectable, changes what every
  user sees and needs its own proposal.
- **A prose linter for documentation.** The writing skills are a review-time norm today. A
  mechanical floor such as textlint could catch long sentences and filler before review.
