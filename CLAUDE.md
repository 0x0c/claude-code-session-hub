# CLAUDE.md — working agreement for AI sessions

Read this first. It is the shared premise every session starts from, whether a person or an agent
runs it.

## What this is

Session Hub lets a parent Claude Code session follow many sub-sessions cheaply. Each sub-session
pushes short status messages to a hub server on the loopback interface. The hub stores them as
append-only events and streams a real-time dashboard to the browser over Server-Sent Events (SSE).
The parent reads a few lines from `session-hub attention` instead of reading transcripts.

| Path | What it holds |
|---|---|
| `session_hub/` | The Python package: schema, event store, hub server, CLI, hooks, collections |
| `session_hub/templates/dashboard.html` | The dashboard page (one self-contained file) |
| `bin/session-hub` | The wrapper that finds the package however it was installed |
| `skills/`, `hooks/`, `prompts/` | What we ship to users' sessions (Claude Code plugin and APM package) |
| `.claude/skills/` | Skills for developing this repository; not shipped |
| `proposals/` | Design proposals, one file per change (`SH-NNNN-<slug>.md`) |
| `docs/DESIGN.md` | The design rationale and the glossary |
| `tests/` | The test suite (standard library `unittest`) |

## How we work: proposal first

Every non-trivial change starts as a proposal under [`proposals/`](proposals/README.md), and the code
follows the proposal. Three skills drive the flow:

- [`ideation`](.claude/skills/ideation/SKILL.md) — shape an idea into a proposal; never write code.
- [`implement-proposal`](.claude/skills/implement-proposal/SKILL.md) — build an `Approved` proposal.
- [`propose-and-build`](.claude/skills/propose-and-build/SKILL.md) — write and build a small, settled
  proposal on one branch.

A typo fix, a test-only change, or a change that a proposal already describes needs no new proposal.

## Writing

- Write code comments, docstrings, documentation, proposals, skills, commit messages, and pull
  request text in **English**.
- Before writing or revising prose, load [`document-writing`](.claude/skills/document-writing/SKILL.md)
  and [`english-document-writing`](.claude/skills/english-document-writing/SKILL.md). They shape the
  draft; they are not a proofreading pass.
- The dashboard labels, the CLI messages, and the text the hooks inject are Japanese product strings
  today. Leave them as they are unless a proposal changes them.

## Ground rules

1. **Keep tokens cheap.** A parent learns the state of its sub-sessions from a few lines, never from
   their transcripts. Anything that wakes a parent or adds text to every turn needs a reason.
2. **Never interrupt a session.** A hook exits 0 on any error and blocks a stop at most once.
3. **The event store is the single source of truth.** Views, collections, and exported files are
   projections of the append-only events.
4. **Stay local.** The hub listens on the loopback interface; we do not expose a user's machine.

## Verify your work

Run the gate before you call a change done, and again before you push:

```bash
scripts/check.sh
```

The script runs the test suite (`python3 -m unittest discover -s tests`) and the proposal format
check (`python3 scripts/proposals.py lint`). Both must pass. For a dashboard change, also open the
page with demo data (`python3 scripts/demo.py --store <dir>`, then
`bin/session-hub --store <dir> serve`) and look at it.

## Git

- Work on a branch, never on `main`. Commit with a scoped message such as `feat(dashboard): …`,
  `fix(hooks): …`, or `docs(proposal): …`.
- Open a pull request only when the user asks for one.
