---
name: propose-and-build
description: Write a small, well-scoped Session Hub proposal and its implementation together on one branch, for a change whose design is already settled.
---

# Propose and build

Write a proposal **and** its implementation on one branch, and land them in a single pull request.
You are the author and the implementer; the test suite and the format check are the judge.

This skill composes the other two rather than restating them:

- [`ideation`](../ideation/SKILL.md) writes a proposal and stops there.
- [`implement-proposal`](../implement-proposal/SKILL.md) builds an `Approved` proposal.
- **`propose-and-build`** does both, for a small change the author is ready to build now.

## When to use it, and when not to

One pull request fuses the design review with the code review: merging it accepts the proposal and
the implementation in a single act. That trade is honest only when the design is settled, because
reworking code against a proposal that review reshapes wastes the work.

- **Good fit:** a contained change the author already holds fully formed — a new command-line interface (CLI) subcommand, a
  small dashboard affordance, a new collection view, a documentation restructure with a little code.
- **Use the two-step path instead** (`ideation`, then `implement-proposal`) when the design is
  uncertain, touches the protocol or the store format, or is likely to change in review.

When in doubt, take the two-step path.

## Workflow

### Phase A — write the proposal

Run [`ideation`](../ideation/SKILL.md) steps 1–5 as written: ground yourself, discuss with the user,
scaffold with `python3 scripts/proposals.py new` (with the author's confirmed handle), fill every
section under the writing skills, and run the cold self-review on the proposal. Create the proposal
with `--status Approved`: the pull request is where the maintainer accepts the design.

### Phase B — build against the proposal

On the same branch, run [`implement-proposal`](../implement-proposal/SKILL.md) steps 2–7, treating
the new proposal as the specification. Run the cold self-review on the whole diff, proposal and code
together, until it comes back empty (at most three rounds).

### Phase C — promote the proposal

Set `Status` to `Implemented`, tick every *Progress* box, and fill the `Implementing PR` row as soon
as the pull request exists, in both language files (`implement-proposal` step 8). Until the user asks for the pull request,
leave `Status` at `In progress` and say that the promotion waits for the pull request number. The
first session that learns the number fills the row and pushes the change, whatever else that session
was asked to do.

## References

- [`ideation`](../ideation/SKILL.md) and [`implement-proposal`](../implement-proposal/SKILL.md) —
  the two skills this one composes.
- [`proposals/README.md`](../../../proposals/README.md) — statuses and format.
