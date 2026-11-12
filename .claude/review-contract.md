# Review contract

This file is the contract for a cold review of a change in this repository: a proposal, code, or
documentation. A reviewer that has not seen the authoring conversation applies it to a diff and
reports findings. The [`ideation`](skills/ideation/SKILL.md),
[`implement-proposal`](skills/implement-proposal/SKILL.md), and
[`propose-and-build`](skills/propose-and-build/SKILL.md) skills run it before every push.

## Inputs

The reviewer receives exactly two inputs: this contract and the diff against the branch point.

```bash
git add -N <new paths>   # record new files without staging their content
git diff "$(git merge-base HEAD origin/main)"
```

Diff against the branch point, not `origin/main` itself. A branch that is behind `origin/main`
would otherwise show every change merged since as a deletion.

## Lenses

Apply every lens that matches the diff.

- **Correctness.** Find inputs or states that produce a wrong result, a crash, or lost data. Name
  the concrete scenario.
- **Protocol and compatibility.** A change to an event field, a `[HUB/1]` line, a Hypertext Transfer Protocol (HTTP) endpoint,
  or a stored file must stay readable by the previous version, or the proposal must say why it
  breaks compatibility.
- **Sessions are not interrupted.** A hook must never fail a Claude Code session: it exits 0 on
  any error, and it blocks a stop at most once. A change that can make a hook exit non-zero, hang,
  or loop is a finding.
- **Token cost.** Anything that adds text to a model's context on every turn, or wakes a parent
  session, must justify the cost.
- **Security.** Untrusted input (a pushed message, a file under the store, a collection
  definition) must not reach a shell, a path outside the store, or the page as HyperText Markup Language (HTML).
- **Tests.** New behavior has a test that fails without the change. The suite still passes.
- **Proposal fidelity.** For an implementation, the code does what the proposal's Detailed design
  says, and a deliberate deviation updates the proposal in the same change.
- **Prose.** Documentation, skills, comments, and proposals follow the
  [`document-writing`](skills/document-writing/SKILL.md) and
  [`english-document-writing`](skills/english-document-writing/SKILL.md) skills. Flag a missing
  contribution statement, an undefined term or acronym, an unresolvable "it" or "this", filler, or a
  sentence that should be a list.
- **Bilingual parity.** A changed user-facing document has its Japanese mirror (`*.ja.md`) updated
  in the same diff, with the same facts and structure, written under
  [`japanese-document-writing`](skills/japanese-document-writing/SKILL.md).

## Output

The reviewer never edits a file. Each finding is one of two kinds:

- a **fix instruction**: the file, the exact location, and the exact change to make; or
- an **escalation**: a finding that calls for a design change, which is the author's decision.

A false positive, or a trade-off that the change already explains, comes back with its rationale and
no instruction. When nothing warrants a finding, the reviewer reports nothing; an empty report is a
complete review.

## The loop

A separate implement pass applies the fix instructions as given, without re-judging them. A fresh
reviewer then reviews the updated diff, with the earlier dismissed findings and their rationale in
its prompt, so the reviewer does not raise them again. Stop when a review comes back empty, or after
three review rounds; if the third round still reports findings, the author decides.

When no subagent is available, the author cannot act as a cold reviewer of their own draft. Run the
review in a separate pass from the edits, and tell the user that the review ran without a cold
reviewer.
