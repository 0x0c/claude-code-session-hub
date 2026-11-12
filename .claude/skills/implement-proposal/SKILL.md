---
name: implement-proposal
description: Build an Approved Session Hub proposal (SH-NNNN) end to end — plan, code, tests, docs, self-review, and status updates. Use when the user names a proposal to implement.
---

# Implement a proposal

Ship one proposal (`proposals/SH-NNNN-<slug>.md`) as working code. The proposal is the
specification; the test suite and the format check are the judge. Converse in the user's language;
write code, comments, documentation, commits, and pull request text in English.

## 1. Pick up the proposal

- Read the proposal in full. Its `Status` must be `Approved`. If it is `Proposed`, ask the user
  whether the design is approved before writing code; if it is `Deferred` or `Rejected`, stop and
  say so.
- Work on the session's branch. If there is none, cut `claude/<slug>` from the latest `origin/main`.
- Set `Status` to `In progress` as the first commit of the branch.

## 2. Ground yourself in the code

Read the modules the Detailed design names, their tests in `tests/`, and the sections of
[`docs/DESIGN.md`](../../../docs/DESIGN.md) that describe them. Note where the proposal is silent or
where the code has moved on since the proposal was written.

## 3. Plan, then confirm

Write a short plan: the files you will change, the tests you will add, and every point where you
must deviate from the proposal. Show the plan to the user and wait for agreement before writing code
when the plan deviates from the proposal or touches the protocol, the store format, or the hooks.

## 4. Build with tests

- Write a failing test for each behavior the proposal adds, then make it pass.
- Keep hooks safe: a hook exits 0 on any error and never blocks a stop more than once.
- Write comments and docstrings in English under the sentence-level rules of
  [`document-writing`](../document-writing/SKILL.md) and
  [`english-document-writing`](../english-document-writing/SKILL.md).
- When the implementation must deviate from the Detailed design, update the proposal in the same
  branch so the proposal stays a true record.

## 5. Update the documentation

Update `README.md`, `docs/DESIGN.md`, and the shipped skills under `skills/` wherever the change
alters behavior a user or an agent relies on. Load the two writing skills before drafting.

## 6. Self-review

Run the cold review in [`.claude/review-contract.md`](../../review-contract.md) against the branch
diff, in two roles: a fresh subagent judges and returns fix instructions or escalations; a separate
pass applies the fix instructions. Repeat until a review comes back empty, at most three rounds.
Bring every escalation to the user before pushing.

## 7. Verify

```bash
python3 -m unittest discover -s tests
python3 scripts/proposals.py lint
```

Both must pass before every push. For a change to the dashboard, also start the hub with demo data
(`python3 scripts/demo.py --store <dir>` and `bin/session-hub --store <dir> serve`) and check the
page in a browser.

## 8. Promote the proposal

In the last commit of the branch, set `Status` to `Implemented` and tick every *Progress* box. The
format check requires the `Implementing PR` row for an `Implemented` proposal, so fill it as soon as
the pull request exists: `[#N](https://github.com/0x0c/claude-code-session-hub/pull/N)`. Open the
pull request only when the user asks for one; until then, leave `Status` at `In progress` and say in
your reply that the promotion waits for the pull request number.

## References

- [`proposals/README.md`](../../../proposals/README.md) — statuses and format.
- [`.claude/review-contract.md`](../../review-contract.md) — the cold-review contract.
