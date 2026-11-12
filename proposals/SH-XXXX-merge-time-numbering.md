**English** · [日本語](SH-XXXX-merge-time-numbering.ja.md)

# SH-XXXX — Number proposals at merge time

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Developer workflow |
| Implementing PR | — |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We stop numbering proposals on branches. `scripts/proposals.py new` names a new pair with the
placeholder id `SH-XXXX`, and the pair keeps that id through review and the merge itself. A GitHub
Actions workflow, `proposal-id`, then runs on every push to `main` that touches `proposals/`. The
workflow gives each placeholder the next free number, renames the files, and commits the result to
`main`. Numbers therefore follow merge order, never collide, and never go to a rejected proposal.

## Motivation

Today `new` takes the next free number when an author creates a proposal. Two branches that start
at the same time see the same `main`, so both take the same number. The format check reports the
duplicate only after one branch merges, and the author of the other branch must then rename two
files and rewrite the id by hand. A proposal that the maintainer rejects keeps its number, so the
sequence on `main` also gains gaps.

Once the change ships, two proposals written in parallel both merge without a rename. After each
merge, a bot commit on `main` turns `SH-XXXX-<slug>.md` into the next `SH-NNNN-<slug>.md`, and the
merged pull request (PR) gets a comment that names the number.

## Detailed design

### The placeholder id

A proposal that has not merged uses `SH-XXXX` wherever its number would appear:

- the file names `SH-XXXX-<slug>.md` and `SH-XXXX-<slug>.ja.md`, and so the language-switch links;
- the title `# SH-XXXX — <Title>`;
- the `Proposal` (`提案`) row of the metadata table.

`proposals.py lint` accepts the placeholder and checks the pair as before. It skips the duplicate
check for placeholders, because two placeholder pairs differ by slug. `new` refuses a slug that
already has a placeholder pair.

### Allocation: `proposals.py allocate`

`allocate` numbers every placeholder pair in the working tree:

1. Collect the numbers in use: the numbered pairs in the working tree, plus the pairs on
   `origin/main` (read with `git ls-tree`). The second set keeps a checkout that lags behind `main`
   from reusing a number.
2. Sort the placeholder pairs by slug, so that every run on every machine gives the same result.
3. For each pair, take the smallest number above every number in use, and rename both files with
   `git mv`.
4. Rewrite the id where it names this proposal: the file name token `SH-XXXX-<slug>`, the title, and
   the metadata row. Every other proposal file that links `SH-XXXX-<slug>` is rewritten too.
5. Print `Allocated SH-NNNN for <slug>` per pair. With no placeholder, print a no-op message.

`allocate` does not replace every `SH-XXXX` in the text. A proposal may discuss the placeholder
itself, as this proposal does, and a blanket replacement would change that prose.

### The guard: `proposals.py guard`

The workflow pushes its commit to `main` with a token that may bypass branch protection, and no PR
or required check stands in front of that push. `guard` is therefore the only gate. It reads the
commit at `HEAD` (`git diff --name-only HEAD~1 HEAD`) and fails when either holds:

- the commit touches a path outside `proposals/`;
- any proposal fails `lint` after the renumbering.

`guard` and `allocate` use the standard library alone, so the privileged job installs no
third-party code.

### The workflow: `.github/workflows/proposal-id.yml`

The workflow runs on `push` to `main` with a path filter on `proposals/**`. It serializes runs with
a `concurrency` group that never cancels a queued run. Its job takes these steps:

1. **Gate.** Continue only when both secrets `AUTOMATION_BOT_APP_ID` and
   `AUTOMATION_BOT_PRIVATE_KEY` exist. Otherwise, log a notice and succeed, so `main` stays green
   while the maintainer sets up the GitHub App.
2. **Token.** Mint a short-lived installation token for the App with
   `actions/create-github-app-token`. The App sits on the bypass list of `main`'s ruleset.
3. **Checkout.** Check out `main` with full history and the App token.
4. **Allocate, guard, push.** Run `allocate`. With no allocation, stop. Otherwise commit as the
   App's bot user, run `guard`, and push to `main`. When the push is rejected because `main` moved,
   fetch, rebase, and retry, up to five attempts.
5. **Comment.** Find the PR of the merge commit and comment the allocated numbers on it. A failure
   here only logs a warning, because the allocation has already landed. The comment is
   approximate: when two proposal PRs merge close together, the first run numbers both and names
   both numbers on the first PR alone. The job checks out `main` rather than the merge commit for
   that reason, so a later run never numbers the same placeholder twice.

The bot's push fires the workflow again. That run finds no placeholder and stops.

Every third-party action is pinned to a full commit hash, with the version in a comment.

### Links from outside `proposals/`

`allocate` rewrites proposal files (`proposals/SH-*.md`) alone, and `guard` rejects any path
outside `proposals/`. A link to
`SH-XXXX-<slug>.md` from any other document, `proposals/README.md` included, would therefore break
at the merge. The `lint` command of `proposals.py` reports such a link; a mention in code is not a
link and passes. An author adds the link once the proposal has a number.

### Documentation

`proposals/README.md` (and its mirror) describes the placeholder, the workflow, the two rules above,
and the secrets. The `ideation` skill tells authors to keep the placeholder and to link a new
proposal from other proposals alone.

## Alternatives considered

- **Renumber on the PR branch.** A workflow could renumber placeholders when a PR opens and commit to
  the PR branch. Two open PRs could still get the same number, the workflow cannot write to a PR from
  a fork, and a rejected PR would burn its number.
- **Detect duplicates in a check alone.** A required check could fail on a duplicate number. That
  check finds the collision earlier, but an author still renames files by hand.
- **Push with the default `GITHUB_TOKEN`.** That token cannot bypass a protected `main`, and its
  pushes do not fire workflows. A dedicated App keeps the bypass narrow and auditable.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (proposals/README.md, the ideation skill)

## References

- [`scripts/proposals.py`](../scripts/proposals.py) — `new`, `lint`, `allocate`, and `guard`.
- [`.github/workflows/proposal-id.yml`](../.github/workflows/proposal-id.yml) — the workflow.
- [`proposals/README.md`](README.md) — the proposal format and how a proposal gets its number.
