**English** · [日本語](SH-XXXX-draft-first-review.ja.md)

# SH-XXXX — Review a pull request when it leaves draft

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Developer workflow |
| Implementing PR | [#48](https://github.com/0x0c/claude-code-session-hub/pull/48) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

Claude Code reviews a pull request (PR) when the PR leaves draft. Every session opens its PR as a
draft, completes the work there, and marks the PR ready.

## Motivation

The ruleset of `main` requires the `claude review` check. The review ran only when a PR opened, so
its check stayed on the first commit, and a later push left the PR blocked. A review that someone
requested with `@claude review` did not help, because GitHub records an `issue_comment` run on the
default branch. PR #45 stayed blocked in this way after a successful review.

Once the change ships, a PR that completes the draft flow carries the `claude review` check on its
head commit, and the review covers the finished work.

## Detailed design

- **Trigger.** The workflow adds `ready_for_review` to `opened` and `reopened`. A push still starts
  no review.
- **Drafts.** The job's condition skips a `pull_request` event on a draft. A person can still comment
  `@claude review` on a draft to ask for an early pass.
- **Sessions.** The Git section of `AGENTS.md` gives every session the same flow:
  1. Open the PR with `gh pr create --draft`, when the user asks for a PR.
  2. Push every commit to the draft, and pass `scripts/check.sh`.
  3. Run `gh pr ready`.
- **Later changes.** A session that must change a ready PR runs `gh pr ready --undo`, pushes the
  complete fix, and runs `gh pr ready` again. This cycle starts one review of the new head commit.
- **Proposal skills.** `ideation`, `implement-proposal`, and `propose-and-build` point to the draft flow. A draft also gives
  a proposal its PR number before the review starts.
- **Limits.** GitHub counts a skipped job as passing. The skipped check of a draft therefore stays green on
  the head commit after `gh pr ready`, until the new review registers its check. A merge in that
  window, such as an automatic merge, skips the review. We accept the window and merge by hand after
  the review. A skipped run that a bot's PR or an ordinary review comment starts may
  still satisfy the requirement, as it could before the change.

## Alternatives considered

- **Review every push.** A `synchronize` trigger would keep the check on the head commit, but each
  intermediate push would spend tokens, and a review could comment on the fix for its own finding.
- **Drop the required check.** A PR could then merge before its review ran.
- **A hook that forces `--draft`.** A hook would miss PRs opened outside the `gh` command. We start
  with the shared instruction, which covers every route.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (AGENTS.md, the proposal skills)

## References

- [`claude-review.yml`](../../.github/workflows/claude-review.yml) — the review workflow.
- [`AGENTS.md`](../../AGENTS.md) — the working agreement.
