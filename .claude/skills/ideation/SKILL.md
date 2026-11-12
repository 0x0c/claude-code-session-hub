---
name: ideation
description: Turn a rough Session Hub feature idea into a proposal under proposals/. Use for proposal authoring and review, never for implementation.
---

# Ideation

A sounding board for shaping a Session Hub idea into a proposal (`proposals/SH-NNNN-<slug>.md`).
You are the author and the thinking partner, not the judge. Converse in the user's language; write
the proposal in English.

## Scope: proposals only — never implement

This skill only authors and shapes proposals. It stops at the files under `proposals/` and, when the
user asks, the pull request that carries them. **Do not write, modify, or refactor product code**
(`session_hub/`, `bin/`, `hooks/`, `skills/`, tests, or configuration), even when the design makes the
implementation obvious or the user nudges toward "just build it".

If the user asks to build the idea, keep this session to the proposal and point to the right skill:

- [`implement-proposal`](../implement-proposal/SKILL.md) builds a proposal once it is `Approved`.
- [`propose-and-build`](../propose-and-build/SKILL.md) writes and builds a small proposal together,
  when its design is already settled.

## Ground rules every idea respects

Read [`CLAUDE.md`](../../../CLAUDE.md) and [`docs/DESIGN.md`](../../../docs/DESIGN.md) before
proposing. Say so when an idea brushes against one of these rules, then reshape the idea to fit:

1. **Keep tokens cheap.** A parent session learns the state of its sub-sessions from a few lines,
   never from their transcripts. Anything that wakes a parent or adds text to every turn needs a
   reason.
2. **Never interrupt a session.** Hooks exit 0 on any error and block a stop at most once.
3. **The event store is the single source of truth.** Views, collections, and files are projections
   of the append-only events, so we can rebuild them from the events.
4. **Stay local.** The hub listens on the loopback interface; we do not expose a user's machine to
   the network.

## Workflow

### 1. Ground yourself in what exists

- `python3 scripts/proposals.py list` and `python3 scripts/proposals.py list --grep <word>` show the
  proposals on a topic. The match covers the full text, so an empty result means the word appears in
  no proposal.
- Read the sections of [`docs/DESIGN.md`](../../../docs/DESIGN.md) that cover the area, and the
  modules under `session_hub/` that implement it, so you never propose something that already exists.
- Check the *Unsorted ideas* list in [`proposals/README.md`](../../../proposals/README.md).

### 2. Ideate with the user

Offer concrete, bounded ideas and ask the questions that sharpen scope: who needs the change, which
part of the system it touches, and how a test could check it. Ask one more question: once the change
ships, what would the user point to and say "it worked"? The proposal's Motivation must name that
observable difference.

### 3. Classify each idea that survives

Tell the user which landing you choose and why.

- **Overlaps an existing proposal.** Extend that proposal instead of creating a duplicate. If the
  existing proposal is already `Implemented`, there is nothing to extend: show the user where the
  behavior already lives.
- **Novel and scoped.** Draft a new proposal (step 4).
- **Still unformed.** Add one bullet under *Unsorted ideas* in `proposals/README.md`.

### 4. Draft the proposal

Scaffold the file with the script; never number a proposal by hand.

```bash
python3 scripts/proposals.py new --slug <slug> --title "<Title>" --topic "<Topic>" --author <handle>
```

**The author is a GitHub handle that the user confirms.** Ask the user for it; never reuse a handle
you saw elsewhere, and never invent one. When nobody can answer (an unattended run), pass
`--author handle`, the literal placeholder, and tell the user that the `Author` row needs the real
handle before the proposal merges; the format check fails until then.

Before drafting the prose, load the [`document-writing`](../document-writing/SKILL.md) and
[`english-document-writing`](../english-document-writing/SKILL.md) skills; they shape the draft. Fill
every `TBD` section: an Introduction that states the contribution up front, a Motivation that names
the observable difference from step 2, a Detailed design precise enough to build from, and the
alternatives you rejected with their reasons.

### 5. Self-review before committing

Run the cold review in [`.claude/review-contract.md`](../../review-contract.md) against the diff of
`proposals/`, in two roles: a fresh subagent that has not seen this conversation judges and returns
fix instructions or escalations, and a separate pass applies the fix instructions. Repeat until a
review comes back empty, at most three rounds. Bring every escalation to the user.

### 6. Verify

```bash
python3 scripts/proposals.py lint
python3 -m unittest discover -s tests
```

Both must pass.

### 7. Commit, push, and open a pull request only when asked

Commit on the session's branch with a scoped message such as `docs(proposal): add SH-0007 push
retry`, and push. Open a pull request only when the user asks for one; its title and body are in
English.

## References

- [`proposals/README.md`](../../../proposals/README.md) — what a proposal is, its statuses, and its
  format.
- [`.claude/review-contract.md`](../../review-contract.md) — the cold-review contract.
