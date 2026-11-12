**English** · [日本語](README.ja.md)

# Proposals

A proposal is a short design document that argues for one change to Session Hub before we build
it. Every non-trivial change starts as a proposal under this directory. Each proposal is a pair of
files: the English original and its Japanese mirror. The proposal records the problem, the design
we chose, and the alternatives we rejected, so a later reader can tell why the code looks the way
it does.

## The lifecycle of a proposal

Each proposal moves through a fixed set of statuses. The `Status` row of its metadata table records
the current one.

| Status | Meaning | Who moves it here |
|---|---|---|
| Proposed | The author wrote the proposal and asks for review. | The author, on creation |
| Approved | The maintainer accepted the design; anyone may build it. | The maintainer, on review |
| In progress | Someone is building it on a branch. | The implementer, when work starts |
| Implemented | The change has landed; the `Implementing PR` row links it. | The implementer, in the implementing pull request (PR) |
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

Scaffold the pair with the script rather than by hand. The script fills the metadata tables from
[`TEMPLATE.md`](TEMPLATE.md) and [`TEMPLATE.ja.md`](TEMPLATE.ja.md) and gives the pair the
placeholder id `SH-XXXX` instead of a number.

```bash
python3 scripts/proposals.py new --slug push-retry --title "Retry pushes with backoff" \
  --title-ja "プッシュの再試行" --topic Protocol --author <github-handle>
```

The command prints the paths of the two new files, for example `proposals/SH-XXXX-push-retry.md`
and `proposals/SH-XXXX-push-retry.ja.md`. Fill every `TBD` section of the English file under the
[`document-writing`](../.claude/skills/document-writing/SKILL.md) and
[`english-document-writing`](../.claude/skills/english-document-writing/SKILL.md) skills, then
write the Japanese mirror under
[`japanese-document-writing`](../.claude/skills/japanese-document-writing/SKILL.md).

### How a proposal gets its number

A proposal keeps the placeholder `SH-XXXX` through review and the merge itself. Picking numbers on
branches would race: two branches open at the same time would take the same number. Instead, the
`proposal-id` workflow (`.github/workflows/proposal-id.yml`) numbers proposals on `main`:

1. A pull request that adds `SH-XXXX-<slug>.md` merges to `main` unchanged.
2. The workflow runs `python3 scripts/proposals.py allocate`. The command gives each placeholder pair
   the next number above every number in use, in slug order, and renames both files with `git mv`.
   It rewrites the id where the id names the proposal: the file names, the title, and the metadata
   row. Prose that mentions the placeholder `SH-XXXX` stays as written.
3. `python3 scripts/proposals.py guard` checks the commit: the commit touches `proposals/` alone,
   and every proposal passes the format check. The workflow then pushes the commit to `main` and
   comments the number on the merged pull request.

Numbers therefore follow merge order, and a rejected proposal never uses one up. Two rules follow:

- Link a new proposal from another proposal by its placeholder file name; `allocate` rewrites those
  links. Do not link it from any other document, this README included, until it has a number. The
  format check reports such a link.
- The workflow commits to `main` as a GitHub App that may bypass the branch protection. Store its id
  and private key in the `AUTOMATION_BOT_APP_ID` and `AUTOMATION_BOT_PRIVATE_KEY` secrets. Until both
  exist, the workflow does nothing and proposals keep their placeholder.

## The format of a proposal

A proposal is a pair of Markdown files: `SH-NNNN-<slug>.md` in English and
`SH-NNNN-<slug>.ja.md` in Japanese. The format check (`python3 scripts/proposals.py lint`) enforces
the rules below on both files.

- **Language switch.** The first line links the other file:
  `**English** · [日本語](SH-NNNN-<slug>.ja.md)` in the English file and
  `[English](SH-NNNN-<slug>.md) · **日本語**` in the Japanese file.
- **Title.** The first heading is `# SH-NNNN — <Title>`, with an em dash.
- **Placeholder id.** Before the merge, `SH-XXXX` stands in for `SH-NNNN` in the file names, the
  title, and the `Proposal` row.
- **Metadata table.** The table between `<!-- SH-METADATA -->` and `<!-- /SH-METADATA -->` holds
  six rows in this order: `Proposal`, `Author`, `Status`, `Topic`, `Implementing PR`, and `Related`.
  - `Author` is the author's GitHub handle as a link. Never guess a handle; ask the author.
  - `Status` is one of the six statuses above, in bold.
  - `Topic` is one of: Protocol, Hub server, Dashboard, Collections, Hooks and skills,
    Distribution, or Developer workflow.
  - `Implementing PR` is `—` until a pull request implements the proposal, then a link to it.
  - `Related` is `—` or links to other proposals.
- **Sections.** Six sections, each under a second-level heading (H2), appear exactly in this order:
  1. *Introduction* states the change and its contribution in one or two paragraphs.
  2. *Motivation* states the problem, why it matters, and one observable difference the change
     will make, so a later reader can check whether the change worked.
  3. *Detailed design* describes the change precisely enough to build and review it.
  4. *Alternatives considered* lists the designs we rejected, each with its reason.
  5. *Progress* is a checklist; an `Implemented` proposal has every box ticked.
  6. *References* links the code, documents, and prior proposals the proposal builds on.
- **The Japanese mirror.** The Japanese file uses Japanese labels for the same six metadata rows
  (提案, 作者, 状態, トピック, 実装PR, 関連) and the same six sections (はじめに, 動機, 詳細設計,
  検討した代替案, 進捗, 参考資料). Every metadata value must match the English file.
- **No placeholders.** No section may still say `TBD` when the proposal is committed.

## List proposals

```bash
python3 scripts/proposals.py list
python3 scripts/proposals.py list --status Approved
python3 scripts/proposals.py list --grep dashboard
```

## Unsorted ideas

Add an unformed idea here as one bullet. Promote it to a numbered proposal once its scope is clear.

- **A prose linter for documentation.** The writing skills are a review-time norm today. A
  mechanical floor such as textlint could catch long sentences and filler before review.
