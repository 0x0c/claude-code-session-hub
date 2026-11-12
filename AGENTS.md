**English** · [日本語](AGENTS.ja.md)

# AGENTS.md — working agreement and field notes

Read this first. It is the shared premise every session starts from, whether a person or an agent
runs it. The first half is the working agreement; the second half, [Field notes](#field-notes),
records what we learned while building Session Hub, so that no session has to learn it again.

## What this is

Session Hub lets a parent Claude Code session follow many sub-sessions cheaply. Each sub-session
pushes short status messages to a hub server on the loopback interface. The hub stores them as
append-only events and streams a real-time dashboard to the browser over Server-Sent Events (SSE).
The parent reads a few lines from `session-hub attention` instead of reading transcripts.

| Path | What it holds |
|---|---|
| `session_hub/` | The Python package: schema, event store, hub server, command-line interface (CLI), hooks, collections |
| `session_hub/templates/dashboard.html` | The dashboard page (one self-contained file) |
| `bin/session-hub` | The wrapper that finds the package however it was installed |
| `skills/`, `hooks/`, `prompts/` | What we ship to users' sessions (Claude Code plugin and Agent Package Manager (APM) package) |
| `.claude/skills/` | Skills for developing this repository; not shipped |
| `proposals/` | Design proposals, one pair of files per change (`SH-NNNN-<slug>.md` and `.ja.md`) |
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
This repository stands on its own: develop everything here, and do not name another project as the
origin of its content.

## Writing

- Write code comments, docstrings, skills, prompts, commit messages, and pull request text in
  **English**.
- User-facing documents are **bilingual**. Each English original `<name>.md` has a Japanese mirror
  `<name>.ja.md` next to it: `README`, `AGENTS`, `docs/*`, `proposals/README`, and every proposal.
  Update both files in the same change. `scripts/check_docs.py` and `scripts/proposals.py lint`
  check that every pair exists, links to each other on its first line, and keeps the same headings.
- Spell out every acronym on its first use in each document: "Server-Sent Events (SSE)", and in
  Japanese 「Server-Sent Events（SSE）」. `scripts/acronyms.py` checks it; add a new acronym to its
  table when you introduce one.
- Before writing or revising prose, load [`document-writing`](.claude/skills/document-writing/SKILL.md)
  and the layer for the language: [`english-document-writing`](.claude/skills/english-document-writing/SKILL.md)
  or [`japanese-document-writing`](.claude/skills/japanese-document-writing/SKILL.md). They shape the
  draft; they are not a proofreading pass.
- The dashboard is localized: every label lives in the `MESSAGES` table of
  `session_hub/templates/dashboard.html`, in English and Japanese, and a change to a label updates
  both. Display strings that the server sends (collection labels and groups) may be a
  `{"en": ..., "ja": ...}` map. The command-line interface (CLI) messages and the text the hooks
  inject are English.

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

The script runs the test suite, the proposal format check (`scripts/proposals.py lint`), the
bilingual-docs check (`scripts/check_docs.py`), and the acronym check (`scripts/acronyms.py`). All
four must pass. For a dashboard change, also
look at the page with demo data, as described under [Field notes](#check-the-dashboard-in-a-real-browser).

## Git

- Work on a branch, never on `main`, unless the user asks you to merge. Commit with a scoped message
  such as `feat(dashboard): …`, `fix(hooks): …`, or `docs(proposal): …`.
- Open a pull request only when the user asks for one.

## Field notes

Each note states a fact we verified, why it matters, and what to do about it.

### Decisions already made

- **Local operation is the supported setup.** Sub-sessions run on the user's machine and share one
  store (`HUB_STORE`). The hub listens on `127.0.0.1`, and sub-sessions push to
  `HUB_URL=http://127.0.0.1:8765`. We do not expose the user's computer to the network, so tunnels
  and public hosting are out of scope.
- **The hub does not send instructions to sub-sessions.** A hook could deliver an instruction to a
  running sub-session, but nothing can wake a sub-session that has ended its turn. The parent
  records an answer with `session-hub answer` and delivers the printed `[HUB/1]` line itself; for a
  `claude -p` child, it resumes the session with `claude -p --resume <session_id> "<line>"`.
- **"Message" means one update from a sub-session to the hub.** A `[HUB/1]` line that a sub-session
  sends to its parent is an *escalation notice*, not a message.
- **Knowledge is a collection, not a feature.** Collections (match, reduce, view, sinks) are
  projections over the event store; the knowledge base is the built-in collection over `finding`
  events. A new way to accumulate updates is a new collection definition, not new storage.

### Claude Code hooks

- A **SessionStart** hook's standard output becomes context for the model. Keep it to a line or
  two, and print nothing when the hub is not configured.
- A **Stop** hook blocks the stop by printing `{"decision": "block", "reason": "..."}`. The next
  invocation receives `stop_hook_active: true`; return nothing then, or the session loops.
- A **PostToolUse** hook with the matcher `TodoWrite|TaskCreate|TaskUpdate` sees the task list in
  `tool_input`, which gives progress without spending model tokens. `TaskUpdate` carries only a task
  id, so we record the id-to-name mapping when `TaskCreate` runs.
- The hook payload includes `transcript_path`. Token usage comes from summing `message.usage` over
  the assistant entries, deduplicated by `message.id`: one response can span several lines.
- Hooks are no-ops unless `HUB_URL` or `HUB_STORE` is set, so the plugin is safe to enable globally.

### Session identity

- In a cloud session, `CLAUDE_CODE_REMOTE_SESSION_ID` holds `cse_<id>`; the session tools use
  `session_<id>`, so we rewrite the prefix. Locally, `CLAUDE_CODE_SESSION_ID` holds a universally unique identifier (UUID), which is
  also the id that `claude --resume` accepts.
- Subagents started with the Agent tool share the parent's session id, so they do not appear as
  separate sub-sessions. A sub-session must be a separate Claude Code process.

### APM (Agent Package Manager) packaging

We verified these facts with APM 0.35.1 by installing this repository into a scratch project.

- APM classifies this repository as a **Claude plugin collection** because `.claude-plugin/` exists.
  Adding `.apm/` or dependencies to `apm.yml` would switch it to the APM layout, so `apm.yml` holds
  metadata alone, and the development skills live in `.claude/skills/`, outside the package.
- APM deploys each skill to `.claude/skills/<folder name>/` **without a namespace**, so a shipped
  skill needs a distinctive folder name (`session-hub-report`, not `report`), and the frontmatter
  `name` must match the folder.
- APM merges `hooks/hooks.json` into the consumer's `.claude/settings.json` and rewrites
  `${CLAUDE_PLUGIN_ROOT}` to `${CLAUDE_PROJECT_DIR}/.claude/hooks/<package>/`. It copies **only the
  files the hook commands name** (`bin/session-hub`), not the Python package; the package lands in
  `apm_modules/<owner>/<repo>/`. That is why `bin/session-hub` searches for the package, and why a
  hook exits 0 quietly when it finds none.
- `apm install <repo> --skill <name>` installs one skill. `bin/` executables deploy only with
  `--trust-bin`.
- Quote values that look like numbers in YAML: `author: 0x0c` parses as the integer 12.

### Store and server

- Each store file has a single writer (`<id>.jsonl` for the sub-session, `<id>@parent.jsonl` for
  the parent), so sharing the store through Git never produces merge conflicts.
- Events written in the same millisecond sorted out of order across writer files. The store now
  hands out strictly increasing timestamps under a store-wide lock (`.clock`).
- A browser's `EventSource` cannot send an `Authorization` header. When a token is set, the page
  accepts `?token=` once, sets an HttpOnly cookie, and redirects to drop the token from the Uniform Resource Locator (URL).
- The server rebuilds the snapshot from the store on every message. That is fine for thousands of
  events; beyond that, switch to incremental updates.

### Dashboard

- Every update re-renders the Document Object Model (DOM), so a Cascading Style Sheets (CSS) animation restarts unless we preserve it. The glow on a
  received message records its start time and sets a negative `animation-delay` on each re-render.
- An element's `hidden` attribute loses to a CSS `display` rule; the stylesheet carries
  `[hidden] { display: none !important; }`.
- `element.style` ignores custom properties set through `Object.assign`; use
  `style.setProperty("--name", value)`.
- A tab that is not shown keeps its old DOM, so clear it when switching away, or stale state (such as
  an expired glow) lingers.

### Check the dashboard in a real browser

- Chromium and Playwright are available in the cloud sandbox: `require('playwright')` works from any
  directory.
- Seed demo data and serve it:

  ```bash
  python3 scripts/demo.py --store /tmp/hub-demo
  HUB_STORE=/tmp/hub-demo bin/session-hub serve
  ```

  Then push live updates with `python3 scripts/demo.py --push http://127.0.0.1:8765`, or run
  `session-hub` commands with `HUB_URL` set.
- Regenerate the README screenshots (`docs/images/`, both languages) with
  `node scripts/screenshots.js` after any visible change to the dashboard. Pick the demo data's
  language with `scripts/demo.py --lang en|ja` and the page's language with `?lang=en|ja`.
- The server runs as `python3 -m session_hub serve`, so stop it with
  `pkill -f "session_hub serve"`; a pattern on `session-hub serve` does not match.

### Repository hygiene

- A bare `.gitignore` pattern matches at any depth: `dashboard.html` once hid
  `session_hub/templates/dashboard.html`, and the dashboard went uncommitted. Anchor a pattern that
  means the repository root with a leading slash (`/dashboard.html`), and check
  `git check-ignore -v <path>` when a file seems missing.
