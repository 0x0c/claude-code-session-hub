**English** · [日本語](SH-XXXX-draft-first-review.ja.md)

# SH-XXXX — Review a pull request when it leaves draft

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Developer workflow |
| Implementing PR | [#48](https://github.com/0x0c/claude-code-session-hub/pull/48) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

Claude Code reviews a pull request (PR) when the PR leaves draft. Every session opens its PR as a
draft, completes and self-reviews the work there, and marks the PR ready.

## Motivation

The ruleset of `main` required the `claude review` check when we found the problem. The review ran only when a PR opened, so
its check stayed on the first commit, and a later push left the PR blocked. A review that someone
requested with `@claude review` did not help, because GitHub records an `issue_comment` run on the
default branch. PR #45 stayed blocked in this way after a successful review.

Once the change ships, a PR that completes the draft flow carries the `claude review` check on its
head commit, and the review covers the finished work.

## Detailed design

- **Trigger.** The workflow adds `ready_for_review` to `opened` and `reopened`. A push still starts
  no review.
- **Drafts and bots.** GitHub counts a skipped job as passing. The job therefore runs on every
  `pull_request` event that starts the workflow, and its first step fails on a draft or on a bot's
  event. A person who marks the PR ready starts a run that should replace the failure on the same
  commit. We have not verified the replacement on GitHub; the Rollout item says when we do.
- **Comments.** A person can comment `@claude review`, on a draft too. A run that a comment starts
  reports as `claude review (requested)`, even when it is skipped, so it neither satisfies nor
  overwrites the required check.
- **Sessions.** The Git section of `AGENTS.md` gives every session the same flow:
  1. Open the PR with `gh pr create --draft`, when the user asks for a PR.
  2. Push every commit to the draft, and pass `scripts/check.sh` on the final commit.
  3. Run the cold review in `.claude/review-contract.md` on the whole branch diff, whatever the size of
     the change. Fix every finding, and repeat with a fresh reviewer until a review comes back empty.
     Write the reason for each dismissed finding in the PR body.
  4. Leave the PR in draft and ask the user when a finding needs a design decision, or when the third
     round still reports findings.
  5. Run `gh pr ready`.
- **Later changes.** A session that must change a ready PR runs `gh pr ready --undo`, pushes the
  complete fix, repeats the self-review, and runs `gh pr ready` again. This cycle starts one review of the new head commit.
- **Proposal skills.** `ideation`, `implement-proposal`, and `propose-and-build` point to the draft flow. A draft also gives
  a proposal its PR number before the review starts.
- **Rollout.** The ruleset does not list `claude review` while this change is in review. The
  maintainer adds the check after the change merges and a draft PR confirms that the success after
  `gh pr ready` replaces the failure on the same commit. Until then, the check blocks no merge.
- **Limits.** A PR from a fork receives no secrets, and an environment without a credential starts no
  review. In both cases the check of a PR that a person marks ready passes without one, as it did before the
  change. A draft or a bot's event fails even then.

## Alternatives considered

- **Skip drafts and bots.** A skipped check passes, so a PR could merge before its review registers,
  or without one when a bot marks it ready. A red check on a draft is the cost of closing both gaps.
- **Review every push.** A `synchronize` trigger would keep the check on the head commit, but each
  intermediate push would spend tokens, and a review could comment on the fix for its own finding.
- **Drop the required check.** A PR could then merge before its review ran.
- **A hook that forces `--draft` and the self-review.** A hook would miss PRs that a session opens or
  marks ready outside the `gh` command. We start with the shared instruction, which covers every route.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (AGENTS.md, the review contract, the proposal skills)
- [ ] Required check added to the ruleset (after a draft PR confirms the replacement)

## References

- [`claude-review.yml`](../../.github/workflows/claude-review.yml) — the review workflow.
- [`AGENTS.md`](../../AGENTS.md) — the working agreement.
