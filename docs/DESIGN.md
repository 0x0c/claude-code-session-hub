**English** · [日本語](DESIGN.ja.md)

# Session Hub design

A parent session (the orchestrator) often runs several child sessions at once. This document designs
a way for the parent and a human to see the state of every child **at a glance** while spending **as
few tokens as possible**. Children report their state to a local hub server. The server stores each
report and pushes it to a real-time dashboard, and the parent reads a few summary lines only when a
child needs it.

> Implementation status: most of phases 0, 1, 3, and 4 in §8 are implemented — the push-based hub
> server, the dashboard with its timeline view, and the reporting skill and hooks.
> For usage, see the [README](../README.md). For terms, see [Appendix A](#appendix-a-glossary).

## 0. Goals and design principles

| Goal | What we want to know |
|---|---|
| Save tokens | The parent never reads a child's transcript and never wakes up without need |
| Know when a human must step in | Whether a child has stopped to wait for a human: a decision, a credential, a permission, or a clarification of the spec |
| Know when a pull request (PR) can go to review | Whether continuous integration (CI), the self-review, and every open item are settled, so the PR can go to review |
| See activity | What each child is doing now, and whether it has stopped (the heartbeat) |
| See remaining work | How many tasks remain, how large they are, and the next step |

We follow six principles:

1. **Pull by default; push to the parent by exception.** A child writes its state to a shared store
   and nothing more. A child wakes the parent — which costs tokens — only on four transitions:
   waiting for a human, ready for review, failed, and done.
2. **Scripts, not the large language model (LLM), aggregate and render.** Generating the dashboard
   is deterministic work and costs zero tokens.
3. **The LLM writes meaning; scripts collect facts.** The child agent writes the phase and the text
   of a question. Hooks and scripts collect the token counts, the commits, the PR and CI state, and
   the last update time on their own.
4. **Fixed schema, enumerated values, short text.** Free text is limited to a one-line summary and
   the text of a question, each with a character limit.
5. **Progressive disclosure.** A reader moves from the list (one line per session) to the detail
   (one JavaScript Object Notation (JSON) record) to the transcript (a link). The parent normally reads only the "needs action"
   lines of the list.
6. **Do not trust self-reports alone.** "Ready for review" requires both the child's own claim and
   a mechanical gate, such as green CI.

---

## 1. What a child records (the status record)

Each session has one status record, a JSON object. The field `v` holds the schema version.

### 1.1 Fields

| Group | Field | Writer | Description |
|---|---|---|---|
| Identity | `v`, `session_id`, `parent_id`, `title`, `task_ref` | At launch (parent) | `task_ref` is an issue number or a task identifier (ID) |
| Location | `repo`, `branch`, `base` | At launch / hook | |
| State | `state` | Child (CLI) | One of the values listed in §1.2 |
| | `phase` | Child | A narrow enumeration such as `plan` / `implement` / `test` / `fix` / `docs` / `self_review` |
| | `summary` | Child | What the child is doing now. **≤ 80 characters** |
| | `next` | Child | The next step. ≤ 80 characters |
| Progress | `tasks.done`, `tasks.total`, `tasks.items[]` | Child or hook | Each item is `{t: "short name", s: "todo|doing|done|skip", size: "S|M|L"}` |
| | `remaining` | Script | The sum of the sizes of the unfinished items (for example S=1, M=3, L=8) |
| Waiting for a human | `attention.kind` | Child | `decision` / `clarification` / `credential` / `permission` / `review` / `external` (for example, waiting for another team) |
| | `attention.question`, `attention.options[]`, `attention.default`, `attention.since` | Child | We recommend offering options: the answer then fits in one word, which cuts the tokens of each round trip |
| | `attention.blocking` | Child | `true`: the child has stopped completely. `false`: the child continues with the default and waits for confirmation |
| Blockers | `blocked_on` | Child | Another session ID or an external cause (`session:xxx`, `ci`, `upstream`) |
| PR | `pr.number`, `pr.url` | Hook | |
| | `pr.ci` | Script | `pending` / `pass` / `fail` / `none` |
| | `pr.mergeable`, `pr.unresolved_threads`, `pr.review` | Script | Fetched from GitHub |
| | `ready.self_review`, `ready.tests_added`, `ready.description` | Child | The child's self-reported checklist |
| | `ready.gate` | Script | The result of the gate in §4 (`ready` / `not_ready:<reason>`) |
| Cost | `usage.input`, `usage.output`, `usage.cache_read`, `usage.cache_write`, `usage.cost_usd` | Hook | The sum of the usage entries in the transcript (`transcript_path`) |
| | `usage.context_pct` | Hook | The share of the context window in use. It detects a session close to compaction |
| Health | `heartbeat` | Hook | The time the last turn ended |
| | `last_error` | Child / hook | The most recent failure (≤ 120 characters) |
| | `confidence` | Child | `high` / `med` / `low`. A human looks at low-confidence sessions first |
| Bookkeeping | `seq`, `updated_at` | CLI | Monotonically increasing. They reject out-of-order and duplicate writes |
| | `links.session`, `links.artifacts[]` | Hook | Links to the transcript and to the deliverables |

### 1.2 `state` values and transitions

```
queued → planning → working ⇄ waiting_ci
                      │  ↑         │
                      ▼  │         ▼
              needs_human ─┘   review_ready → in_review → changes_requested ─┐
                      │                          │                       │
                      ▼                          ▼                       │
                   blocked                     done (merged)   ←── working ┘
any state → failed / abandoned
```

| state | Meaning | Wakes the parent? |
|---|---|---|
| `queued` | Waiting to start | No |
| `planning` / `working` | Working | No |
| `waiting_ci` | Waiting for CI (the child is free) | No |
| `needs_human` | Needs a human decision | **Yes** |
| `blocked` | Waiting for another session or an external cause | Only if it lasts long (a script decides) |
| `review_ready` | May go to review (confirmed only when the gate passes) | **Yes** |
| `in_review` / `changes_requested` | Under review / addressing review comments | Only when comments arrive |
| `done` | Finished | **Yes** (several are batched into one message) |
| `failed` / `abandoned` | Failed / abandoned | **Yes** |

### 1.3 Example record

```json
{
  "v": 1, "session_id": "session_01ABC", "parent_id": "session_01PARENT", "seq": 42,
  "title": "Rate limiting for the auth API", "task_ref": "#128",
  "repo": "owner/app", "branch": "claude/rate-limit", "base": "main",
  "state": "needs_human", "phase": "implement", "confidence": "med",
  "summary": "Implementing with Redis. Waiting for the limit value",
  "next": "After the answer, wire it into the middleware and add tests",
  "tasks": {"done": 3, "total": 6, "items": [
    {"t": "Design", "s": "done", "size": "S"},
    {"t": "Middleware", "s": "doing", "size": "M"},
    {"t": "Tests", "s": "todo", "size": "M"}
  ]},
  "remaining": 7,
  "attention": {"kind": "decision", "blocking": true, "since": "2026-11-12T03:10:00Z",
    "question": "Limit per minute?", "options": ["60", "120", "300"], "default": "120"},
  "pr": {"number": null, "ci": "none"},
  "ready": {"self_review": false, "tests_added": false, "description": false, "gate": "not_ready:no_pr"},
  "usage": {"input": 182000, "output": 21000, "cache_read": 1450000, "cost_usd": 1.92, "context_pct": 38},
  "heartbeat": "2026-11-12T03:10:05Z", "updated_at": "2026-11-12T03:10:05Z"
}
```

---

## 2. Comparing the transports

A transport is the path a status update travels. We compared nine candidates.

| Transport | Direction | Parent tokens | Latency | Durability | Readability for humans | Notes |
|---|---|---|---|---|---|---|
| **A. A dedicated Git branch** (orphan `hub/status`, one file per session) | Child → store | 0 | Low (push interval) | High (history = event log) | Medium | Works in any environment. One file per session nearly avoids conflicts. On a failed push, rebase and retry |
| B. A status file inside the working branch | Child → store | 0 | Low | High | Low | Not recommended: it pollutes the PR diff |
| **C. An Artifact's shared database** (ArtifactData) | Child → dashboard | 0 | High | Medium | **High** (a web page as is) | If the dashboard itself is an Artifact, rendering is instant too. Assumes child sessions can write with the same account |
| D. `send_message` (child → parent) | Child → parent | **Every time** (a parent turn runs) | Highest | Low (conversation only) | Low | Reserve for escalation |
| E. `send_message` (parent → child) | Parent → child | Child side only | Highest | Low | — | For answers and instructions (commands) |
| F. GitHub labels / PR body / issue comments | Child → GitHub | 0 | Medium | High | High (on GitHub) | Labels such as `hub:needs-human` work with GitHub notifications. Unusable before a PR exists |
| G. Polling the cloud session application programming interface (API) (`status_bucket` from `get_session`, `list_events` filtered by `kinds`) | Parent fetches | Small to large | Medium | — | — | The ground truth, with no cooperation from the child. These are Model Context Protocol (MCP) tools, so the LLM must call them, and `list_events` is heavy. Limited to `get_session`, polling stays cheap |
| H. Local transcripts (`~/.claude/projects/**/*.jsonl`) | A script reads them directly | 0 | High | High | — | Local parallel runs only. Yields facts such as usage and the last tool call |
| **I. Hypertext Transfer Protocol (HTTP) push to a hub server** (`POST /api/events`) | Child → server → browser | 0 | **Highest** (delivered on receipt) | High (the server appends to the store) | **High** | The child must be able to reach the server (§9) |

### Decision: push (I) is the main transport

We first recommended polling a Git store (A). We switched to push to make the **dashboard update
immediately**.

- **Child → hub**: on every state change, the child POSTs an event to the hub server with the
  `session-hub` command (I). The server validates the event, appends it to the store, and delivers
  it at once over Server-Sent Events (SSE) to every connected browser. **Neither the server nor the
  browser polls.**
- **When delivery fails**: the child keeps the unsent events in an outbox (a local JSON Lines (JSONL) file) and
  resends them first on the next send.
- **Durability**: the store is append-only JSONL. When needed, the store can also be shared and
  archived through Git, as in A (the auxiliary `--pull-every` option).
- **Escalation**: D, used only on transitions that should wake the parent (§3.3).
- **Answers and instructions**: E.
- **Liveness ground truth**: the parent calls `get_session` (G) only when needed and compares its
  `status_bucket` with the reported state.
- **Notifying humans**: browser notifications from the dashboard, with F's labels as a supplement.

## 3. Protocol

### 3.1 Components

```
┌──────────── Child session ─────────────┐
│ Agent ───────── session-hub report ... ─┐   Meaning: state / phase / summary / question
│ Stop hook ───── session-hub hook stop ─┤   Facts: heartbeat / token usage (0 tokens)
│ PostToolUse ─── session-hub hook todo ─┤   TodoWrite etc. → progress (0 tokens)
│                                        ▼
│                    POST /api/events ─────────────┐   On failure, saved to the outbox and resent next time
│ Key transitions only ── send_message ───► parent (1 line)
└────────────────────────────────────────┘          │
                                                     ▼
┌──────────── Hub server (session-hub serve) ────────────────┐
│ Validate → assign seq / time → append to store (events/*.jsonl) │
│ → fold into state, push the diff to browsers over SSE at once   │
└───────────────┬─────────────────────────────────────┘
                ▼ GET /api/stream (SSE)           ▲ GET /api/snapshot
         Browser dashboard                   Parent: session-hub attention
```

- **Event sourcing**: the hub never stores state. The hub folds the append-only event sequence into
  the state on every read. The event sequence is also the source data of the timeline view, so a
  reader can trace exactly what changed and when.
- **One file per writer**: `events/<session_id>.jsonl` holds the child's events, and
  `events/<session_id>@parent.jsonl` holds the parent's answers and instructions. Each file always
  has a single writer, so sharing the store through Git causes no conflicts.
- **Timestamp assignment**: the server assigns a millisecond timestamp that increases monotonically
  across the whole store. The arrival order and the display order therefore always agree.
- **Deleting a session**: the one exception to append-only writing. `session-hub delete` and the
  dashboard's **Delete session** button call `DELETE /api/sessions/<session_id>`, which unlinks every
  file of that session under the files' write locks and pushes the removal to every browser. The
  operation works on whole sessions alone, so the folded state of every other session stays intact
  ([SH-0001](../proposals/SH-0001-delete-session.md)).

### 3.2 Child → hub (`session-hub report` and related commands)

We ask a child agent for one thing alone: run a one-line Bash command whenever its state changes.
`skills/session-hub-report/SKILL.md` gives the procedure.

```bash
session-hub start --title "Rate limiting for the auth API" --task-ref "#128" --task "Design=todo:S" --task "Implement=todo:M"
session-hub report --phase implement --summary "Implementing the middleware" --task "Implement=doing"
session-hub ask --kind decision --q "Limit per minute?" --opt 60 --opt 120 --opt 300 --default 120
session-hub pr --number 45 --ci pending --state waiting_ci
session-hub ready --self-review --tests --description
session-hub done --summary "PR #45 merged"
```

- With `HUB_URL` set, the command pushes to the hub. Without it, the command writes to the local
  store (`HUB_STORE`).
- The server validates each event, truncates text to its limit, and assigns `seq` and the
  timestamp. The server rejects an invalid value with HTTP 400, and the child sees the valid
  candidates.
- A child calls the command **only on a state transition, on a new question, and at PR milestones**.
- Hooks cover any report the child forgets (§3.6).

### 3.3 Child → parent (escalation notices)

A child wakes the parent only on the transitions below. The notice is one line in a fixed format;
the parent reads the details from the store.

```
[HUB/1] <session_id> <event> <short text ≤ 80 characters>
```

| event | Example | `send_message` priority |
|---|---|---|
| `needs_human` | `[HUB/1] session_01ABC needs_human Waiting for the limit value (60/120/300)` | `later` (`next` if `blocking`) |
| `review_ready` | `[HUB/1] session_01ABC review_ready PR#45 CI green` | `later` |
| `failed` | `[HUB/1] session_01ABC failed Test environment does not start` | `next` |
| `done` | `[HUB/1] session_01ABC done PR#45 merged` | `later` |

- The parent's instructions (CLAUDE.md or similar) state one rule: on a message that starts with
  `[HUB/`, run `session-hub attention` without reading the body closely.
- The platform treats a message between sessions as "data from a peer". The parent therefore never
  follows instructions inside such a message and treats the message purely as a status notice. This
  rule protects the parent against prompt injection.
- No repeated notices for the same event: the CLI records the last notice and does not resend for
  the same `(state, attention.question)`.

### 3.4 Parent → child (commands)

```
[HUB/1] cmd=<command> [key=value ...]
```

| command | Purpose |
|---|---|
| `answer q=<id> v=<value>` | Answer a question (return the chosen option's value, nothing more) |
| `report` | Ask the child to resend its latest state (when the heartbeat has lapsed) |
| `pause` / `resume` | Pause / resume |
| `rebase base=main` | Tell the child to catch up with the base branch |
| `abort reason=...` | Stop the work |

### 3.5 The parent's routine (minimizing tokens)

1. The parent waits. The parent runs `session-hub attention` only when a `[HUB/1]` message arrives
   from a child. With `HUB_URL` set, the command reads the server's snapshot.
2. The parent calls `get_session` to check liveness only when a session is suspected stale (`ST`).
   As a rule, the parent does not call `list_events`.
3. The parent reads the output of `attention` alone: the "needs action" lines, normally a few. A
   human reads the full list and the timeline on the dashboard.

### 3.6 Making sure children report on time

Under push, the dashboard stays stale until a child reports. We therefore guarantee what is sent
and when in three layers.

| Layer | Mechanism | Tokens | What it guarantees |
|---|---|---|---|
| 1. Automatic sends (hooks) | The `Stop` hook sends the heartbeat and the token usage. `PostToolUse(TodoWrite, TaskCreate, TaskUpdate)` sends the progress and the name of the task in progress, and moves planning→working when work starts | 0 | Whether the child is alive, and how far it has progressed |
| 2. Instructions (skill + launch prompt) | `skills/session-hub-report/SKILL.md` (a table of when to send what) and `prompts/child-append-system-prompt.md` (five standing rules). If the session is not registered, the `SessionStart` hook injects two lines that prompt the child to run `start` | Small | The meaning: the phase, questions, the PR, and completion |
| 3. Guard at the end of a turn | When a child is about to end its turn while its last reported state is still planning or working, or while it is still unregistered, the `Stop` hook blocks **once** and asks the child to report. `stop_hook_active` prevents an endless loop, and `HUB_STOP_GUARD=0` turns the guard off | One turn (only when needed) | No session left marked as working. The spinner stays truthful |

- The hooks do nothing when neither `HUB_URL` nor `HUB_STORE` is set. Leaving the plugin always
  enabled therefore does not affect other work.
- A hook never stops a session over a network failure or an exception: the hook queues the event in
  the outbox, or exits silently with code 0.
- The guard reads "what the child last reported" from the child's local state
  (`~/.cache/session-hub/state-<id>.json`) and uses no network.

### 3.7 Collections: where updates accumulate and how they are shown

Apart from per-session status, some information belongs **in one place across sessions**: the
findings, caveats, and decisions that work uncovers. We do not build a dedicated feature for that
information. Instead, we generalize "where received updates accumulate" into a **collection**.

```
             ┌─ match ──┐   ┌── reduce ───┐   ┌── view ──┐
Event stream ┤ which    ├──►│ how to      ├──►│ how to   ├──► dashboard tab
(sole source │ events   │   │ combine:    │   │ show:    │
 of truth)   │ to take  │   │ log/latest/ │   │ cards/   │
             └──────────┘   │ aggregate   │   │ table    │──► sinks (written to Markdown / JSONL)
                            └─────────────┘   └──────────┘
```

- **The event store is the sole source of truth.** A collection is a projection on top of the
  store. Changing a collection's definition rebuilds the collection from past events. Adding
  another destination does not change how children send (the protocol).
- **Definitions are declarative JSON** (`collections.json` at the root of the store). A user adds,
  overrides, or disables a collection without writing code.

| Element | Content | Example |
|---|---|---|
| `match` | Which events to collect: `type`, `kind`, `tags_any`, `session`, `status` | `{"type": ["finding"], "kind": ["decision"]}` |
| `reduce` | How to combine: `log` (keep the time series), `latest` (the newest one per key), `aggregate` (merge into one per key) | Knowledge uses `aggregate` with the key `key\|title` (the title when no explicit key is given) |
| `view` | How to display: `cards` (grouped by `group_by`), `table` (with the given `columns`) | Knowledge shows cards grouped by kind |
| `sinks` | Extra destinations: `markdown` / `jsonl` (a path inside the store). A sink file is rewritten only when its content changes | Keep `KNOWLEDGE.md` up to date and publish it in a repository or a wiki |

**Merge rules for `aggregate`**: the latest report overwrites fields such as the body, but an empty
value never overwrites. `tags` and `scope` become the union of all reports, and every reporter is
kept. When several sessions hit the same caveat, their reports merge into one item that reads, for
example, "2 sessions / 2 reports". The count serves as a natural measure of importance. Sending the
same title with `status: obsolete` marks the item obsolete. An obsolete item leaves the default view
and the `knowledge` output, but its history remains.

**The built-in "knowledge" collection** aggregates the `finding` events that children send with
`session-hub learn`.

| `kind` | Display name (on-screen label) | What it records |
|---|---|---|
| `caveat` | Caveat (注意点) | A trap that catches anyone who does not know it |
| `issue` | Open issue (未解決の問題) | A problem found outside the child's own task and left as is |
| `decision` | Decision (決定事項) | Something decided or answered, with the reason |
| `howto` | How-to (手順・ノウハウ) | Steps to reproduce, set up, or investigate |
| `insight` | Insight (知見) | A fact learned about the design, performance, or spec |

A `finding` has the fields `{kind, title(≤80), body(≤600, newlines allowed), tags[], scope, key, status}`.

**Reading knowledge (saving tokens)**: before starting work, a child runs
`session-hub knowledge --scope <the area it will touch>` and reads the relevant items in a few
lines. When the parent launches a new child, the parent adds only the relevant items to the
`prompt`. Neither ever loads every item into its context.

**Example definition** (`collections.json`):

```json
[
  {"name": "knowledge", "sinks": [{"type": "markdown", "path": "KNOWLEDGE.md"}]},
  {"name": "decisions", "label": "Decision log",
   "match": {"type": ["finding"], "kind": ["decision"]},
   "reduce": {"type": "log", "payload": "finding"},
   "view": {"type": "table", "columns": ["title", "body", "reporters", "last_ts"]}},
  {"name": "prs", "label": "PR status", "match": {"type": ["pr"]},
   "reduce": {"type": "latest", "key": ["session_id"]},
   "view": {"type": "table", "columns": ["session_id", "pr", "last_ts"]}}
]
```

### 3.8 Local operation (the current setup)

| Item | Content |
|---|---|
| Where children run | On the user's own computer: `claude` sessions a human starts side by side, or sessions the parent starts in the background with `claude -p --append-system-prompt ...` |
| Shared settings | In the `env` of `~/.claude/settings.json`: `HUB_URL=http://127.0.0.1:8765`, `HUB_STORE=~/.session-hub`, `HUB_AUTOSTART=1` |
| Server | Listens on 127.0.0.1 alone (no token needed). With `HUB_AUTOSTART=1`, the SessionStart hook of the first session to start launches the server in the background. Competition for the port prevents a second instance |
| Message delivery | 1. Push to the server (shown at once). 2. If the push fails, write directly to the shared store. 3. If no store is set either, queue in the outbox |
| Messages sent while the server is down | Kept in the store, so none are lost. They appear on screen when the server starts, on the next push, or at the re-check every 30 seconds |
| Notifying the parent | Send the `[HUB/1]` line through local inter-session messaging, where available. Otherwise a human notices through the dashboard's browser notifications and the tab title (the count of sessions that need action) |
| Installation | With the Agent Package Manager (APM): `apm install 0x0c/claude-code-session-hub --target claude` (per project: skills go to `.claude/skills/`, hooks to `.claude/settings.json`, and the package itself to `apm_modules/`), or as a Claude Code plugin |
| Check | `session-hub doctor` |
| Caveat | A subagent of the Agent tool shares the parent's session ID, so the dashboard does not show the subagent as a separate session. If needed, pass a unique ID with `--session` |

## 4. Checks that scripts decide mechanically

### 4.1 The review gate (`ready.gate`)

The gate confirms `review_ready` only when every condition below holds. Otherwise the gate records
the first condition that failed.

1. A PR exists and is not a draft (or is about to leave draft).
2. CI is `pass`.
3. `mergeable` is true: no conflicts, and the branch is not far behind the base.
4. No review thread is unresolved.
5. `attention` is empty.
6. The child's self-reports `ready.self_review`, `ready.tests_added`, and `ready.description` are
   all true.
7. No `todo` or `doing` item remains in `tasks` (`skip` is allowed).

### 4.2 Detecting stalls and anomalies

| Condition | Verdict |
|---|---|
| `state=working` and `heartbeat` is N or more minutes old | `stale?` — the parent checks with `get_session` |
| `get_session.status_bucket=failed` but `state≠failed` | The child crashed before it could report |
| `needs_human` for M or more hours | Shown with a higher priority |
| `usage.context_pct` > 80 | Consider compacting or splitting the work |
| `usage.cost_usd` exceeds the budget, or is too high for the progress | Efficiency is shown as `cost_usd / tasks.done` |
| The remaining `tasks` do not shrink for a long time | Possibly looping or lost |

### 4.3 Priority (the dashboard's sort order)

`needs_human(blocking)` > `failed` > `review_ready` > `stale?` > `needs_human(non-blocking)` > `changes_requested` > `blocked` > `working` > `waiting_ci` > `done`

---

## 5. Dashboard

The dashboard is localized into English and Japanese. It follows the browser's language, and a
header button or the `?lang=en` / `?lang=ja` parameter switches it. Where this section quotes a
label, it gives the English label and the Japanese label in parentheses.

### 5.1 Output formats

| Format | Use |
|---|---|
| The dashboard of `session-hub serve` | For humans. Reflects each push as it arrives (SSE) |
| `session-hub export --out dashboard.html` | A standalone HyperText Markup Language (HTML) file with an embedded snapshot (for sharing and archiving; does not update) |
| `GET /api/snapshot` | JSON for machines |
| `session-hub attention` | For the parent LLM. Sessions that need action alone, one line each |
| `session-hub log [<session_id>]` | Follow the timeline in a terminal |

### 5.2 Screen layout

- **Header**: the connection status (real-time / reconnecting / polling), the number of sessions,
  the number that need action, the number working, the token total, and the last update.
  - The tab title also shows the "needs action" count, as in `(3) Session Hub`.
  - Optional browser notifications announce transitions to waiting for a human, ready for review,
    failed, done, and stale.
- **Session list** (left): split into "needs action" (要対応), "working or waiting"
  (作業中・待機), and "done" (完了), each sorted by the priority in §4.3.
  - Each card shows a state badge, a task progress bar, the remaining work, the PR and CI, the
    tokens and cost, the last update, and any unanswered question (with its options, its default,
    and the command to answer it).
  - **A session in an active state (planning / working / changes_requested) shows a spinner.**
    A session that is merely waiting (for CI, on a blocker, or for a human) shows no spinner, and
    neither does a session suspected stale.
  - A "ready for review" claim that rests on the self-report alone, without passing the gate (§4.1),
    shows as "Not yet reviewable" (レビュー条件未達) together with the unmet reason.
- **Timeline** (right): traces the reports from children in time order, in two forms.
  - **Feed**: events grouped by date. Each row shows the time, the session, the type, the text, and
    what the event changed (state A→B, phase, task count, a resolved question).
    "Details" (詳細) opens the raw event JSON. New events are highlighted. While the reader is
    scrolled down, a "N new" bar (新着 N 件) announces new events instead of moving the screen.
    Filters: session, event type, full-text search, heartbeat display (consecutive heartbeats
    collapse into one row), and newest or oldest first.
  - **Swimlanes**: one horizontal band per session, with state changes drawn as colored spans.
    Dots mark events (question = orange, answer = blue). Hovering shows details, and clicking jumps
    to the matching feed row. A long wait for a human, or a stall, is visible at a glance.
- **Collection tabs** (right panel): each defined collection adds a tab automatically, for example
  "Knowledge (6)" (ナレッジ (6)).
  - A `cards` view shows one card per item, grouped (knowledge is grouped by kind). Each card shows
    the body, the tags (click one to search), the scope, the reporting sessions and their count, and
    the last update.
  - Clicking a reporting session's name jumps to that event in the timeline. Filters cover the
    session, full-text search, and the group, and a toggle shows obsolete items.
  - An item that arrives by push is highlighted in place.
- **Glow on message arrival**: when a message arrives from a sub-session, four elements glow for
  about six seconds in the color of the new state (waiting for a human = orange, failed = red, ready
  for review = green, and so on):
  - the session's card
  - the matching timeline row
  - the swimlane band
  - the collection item the message landed in

  A glow survives a redraw and continues where it left off. When messages arrive back to back, the
  latest one restarts the glow. Heartbeats (the hooks' automatic sends) do not glow. With the
  reduced-motion setting (prefers-reduced-motion), the glow does not pulse and shows only an
  outline.
- The dashboard reads without horizontal scrolling at phone width (390px), in both light and dark
  themes.

### 5.3 Output of `session-hub attention` (what the parent reads)

Each line starts with a two-letter code: `NH` (needs human), `FL` (failed), `RR` (review ready), or
`ST` (stale).

```
NH session_01ABC #128 decision q=4 "Limit per minute?" [60|120*|300] 38m
FL session_04XYZ npm ci failed with ERESOLVE (peer dependency conflict)
RR session_01DEF #131 PR#45 ci=pass CI green, self-review done
ST session_01GHI 47m since heartbeat
```

## 6. More ways to save tokens

| Measure | Effect |
|---|---|
| The child passes its state as CLI arguments instead of summarizing its transcript | Fewer output tokens for the child |
| Questions come with options and a default | A round trip with a human or the parent shrinks to one word |
| Use `attention.blocking=false` (for a decision the child can proceed on with the default and revise later) | Less waiting, and therefore less wasted cost on resuming |
| As a rule, the parent does not call `list_events` (if it must, it filters `kinds` to `result`) | Fewer input tokens for the parent |
| Batch notices (several `done` notices go out as one message, and so on) | The parent wakes less often |
| Choose the child's model and effort by task size (`size`) | Lower unit cost |
| Record usage with hooks and show the cost per task | Reveals expensive patterns |
| The Stop hook asks a child that has not reported to report, once | Prevents missed reports. The prompt costs one turn, so the hook fires only when the state changed without a report |

---

## 7. Code layout

```
claude-code-session-hub/
  session_hub/            Python package (standard library only)
    schema.py             Schema definition, validation, folding, and the review gate
    store.py              Append-only event store (JSONL per writer, monotonic time, Git sync)
    core.py               Recording and escalation decisions (shared by the CLI and the server)
    client.py             Push client (resends through the outbox)
    deliver.py            Message delivery shared by the CLI and hooks (push → shared store → outbox)
    server.py             Hub server (POST intake, SSE delivery, token authentication)
    view.py               Data assembly for the dashboard / attention / log / knowledge
    collections.py        Collection definitions (match / reduce / view / sinks) and projection
    hooks.py              Claude Code hook handlers (session-start / stop / todo)
    local_state.py        The child's local state (last reported state, task ID mapping)
    usage.py              Token totals from the transcript
    cli.py                The session-hub command
    templates/dashboard.html
  bin/session-hub         Wrapper that needs no installation
  .claude-plugin/         Claude Code plugin definition (plugin.json, marketplace.json)
  apm.yml                 APM metadata alone (no .apm/ or dependencies, so APM distributes the plugin layout as is)
  hooks/hooks.json        The plugin's hook settings
  skills/session-hub-report/       Skill for child sessions (when to report what)
  skills/session-hub-orchestrate/  Skill for the parent session (launch, respond, check)
  prompts/child-append-system-prompt.md   Short standing rules passed to create_session
  scripts/demo.py         Demo data and simulated pushes
  tests/
```

## 8. Phased plan

| Phase | Content | Status |
|---|---|---|
| 0 | Schema, reporting commands, store, and list | Implemented |
| 1 | Automatic usage and heartbeat recording in the Stop hook; TodoWrite integration | Implemented |
| 2 | Fetch PR, CI, and review-comment counts from GitHub automatically and run the gate | The gate logic is implemented. Fetching is manual alone, through `session-hub pr` |
| 3 | Escalation notices and the parent's operating rules | Implemented (`[HUB/1]` line output, the orchestrate skill) |
| 4 | Real-time dashboard and timeline view | Implemented (push + SSE) |
| 5 | Stall detection, budget alerts, and batched notices | Stall detection alone is implemented |
| 6 | Collections (an abstraction of where updates accumulate, such as knowledge) | Implemented (built-in "knowledge", collections.json, Markdown / JSONL sinks) |

## 9. Open questions

1. **Where the hub server runs**: **decided — local operation for now.** Sub-sessions run on the
   user's own computer, and every session shares one `HUB_STORE`.
   - The hub server listens on `127.0.0.1` alone, and children push to
     `HUB_URL=http://127.0.0.1:8765`. The computer is never exposed to the outside.
   - While the server is down, children write directly to the shared store. Their messages appear
     on screen when the server starts or on the next push (§3.8).
   - For cloud child sessions, two candidates remain for future study: a permanent server, and an
     Artifact's shared database.
   - Either way, the child environment's network allowlist should include that host, and the token
     should be registered as a network secret rather than an environment variable.
2. **Execution environment**: will children be mainly cloud sessions (`create_session`), or will
   local parallel runs count too? For local runs alone, sharing `HUB_STORE` is enough.
3. **Fetching GitHub data automatically** (phase 2): should the server call the GitHub API, or
   should the parent fetch the data and record it with `session-hub pr`?
4. **Scope of automation**: on `review_ready`, should the hub also take the PR out of draft and
   assign reviewers?
5. **Budget**: a cost cap per session and overall, and what happens when it is exceeded (notify
   alone, or stop). Today the hooks record token counts alone; the dollar amount is optional
   (`--cost`).
6. **Curating knowledge**: similar findings with different wording become separate items. Is it
   enough for the parent (or a human) to merge them periodically with `--key` and retire them with
   `--obsolete`, or do we need a mechanism that groups items by similarity?
7. **Instructions from the hub to sub-sessions**: decided not to implement. A hook can deliver an
   instruction to a working sub-session, but nothing can wake a stopped one; that takes a
   `send_message` from the parent or a human. We keep the current approach: the parent records the
   instruction with `session-hub answer` / `command` and sends the printed line with `send_message`.
8. **Scale**: the hub rebuilds the state from every event on each receipt. That approach holds up
   to a few thousand events; beyond that, we switch to incremental updates.

---

## Appendix A. Glossary

### Actors and components

| Term | Meaning |
|---|---|
| Parent session (orchestrator) | The session that launches child sessions and makes decisions such as answering questions and requesting reviews. Together with the human watching the dashboard, it is sometimes called "the parent side" |
| Child session / sub-session | A session that does work delegated by the parent and reports its status to the hub |
| Hub / hub server | The server that `session-hub serve` runs. It receives reports from children, stores them, and delivers them to browsers |
| Store | The directory that holds events (`HUB_STORE`, default `.hub`). The files `events/*.jsonl` are its core |
| Dashboard | The web page the hub serves, made of the session list and the timeline |
| `session-hub` | This tool's command. It handles a child's reports, the parent's checks and answers, starting the server, and the hooks |
| Plugin | This repository loaded as a Claude Code plugin. It distributes the skills, hooks, and command to child sessions together |

### Data and protocol

| Term | Meaning |
|---|---|
| Message | One update that arrives at the hub from a sub-session. Once stored, a message becomes one event. On receipt, the dashboard makes the related elements glow for a while. A `send_message` to the parent (a `[HUB/1]` line) is called an "escalation notice" to keep the two apart |
| Glow | The highlight shown when a message arrives. The sender's session card, the matching timeline row, the swimlane band, and the collection item the message landed in glow for about six seconds in the color of the new state (heartbeats excluded) |
| Event | One report (one JSON line) from a child or the parent. Types: start / report / ask / answer / command / ready / pr / heartbeat / done / fail / finding |
| Status (status record) | A session's current state. The hub computes the status by applying the events oldest first (folding) and never stores it |
| Fold | Applying events one by one, in order, to compute the latest state |
| Event sourcing | A design that appends what happened instead of storing state, and computes state from what happened. This design is why the timeline can be traced |
| Append-only | A storage discipline: an event, once written, is never rewritten. The single exception deletes a whole session on request (§3.1) |
| Writer | The owner of an event file. The child writes `<id>.jsonl`; the parent's answers and instructions go to `<id>@parent.jsonl` |
| seq | A sequence number per writer file. An event ID is `<file name>#<seq>` (for example `session_01ABC#3`) |
| state | A session's state, one of the 12 values in §1.2. Examples: working, needs_human, review_ready |
| phase | The stage of work: plan / implement / test / fix / docs / self_review and so on |
| attention | A question to a human or the parent. It holds a kind, the question text, options, a default, and whether the child has stopped (blocking) |
| qid | A question's number. An answer names the question it answers by its qid |
| blocking / non-blocking | A question the child has stopped for until it is answered / a question the child proceeds past with the default |
| tasks / progress / remaining | The task list, and the done and total counts. The remaining work is the sum of the sizes of the unfinished tasks (S=1, M=3, L=8) |
| heartbeat | An automatic event that shows the session is still alive. It also carries the token usage |
| usage | Token usage (input / output / cache_read / cache_write), optionally with the cost and the context usage |
| `HUB/1` | The format of messages between parent and child, and its version: `[HUB/1] <id> <state> <short text>` (child → parent) and `[HUB/1] cmd=<command> ...` (parent → child) |
| Escalation (notice) | A one-line message a child sends to the parent, only on a transition that should wake the parent (waiting for a human, ready for review, failed, done) |
| Command (cmd) | An instruction from the parent to a child: answer / report / pause / resume / rebase / abort |

### Verdicts and display

| Term | Meaning |
|---|---|
| Needs action | A session where a human or the parent should do something: waiting for a human, failed, ready for review, or suspected stale |
| Review gate | The mechanical check of whether a PR may go to review: a PR exists, CI passes, no conflicts, no unresolved comments, no unanswered questions, self-checks done, and no remaining tasks (§4.1) |
| Review conditions not met | The child claimed "ready for review", but the gate did not pass. The dashboard shows the unmet reason |
| Self-report / self-check | What a child declares with `session-hub ready`: the self-review, added tests, and the PR description are done |
| Stale | A session that should be working but has not reported for a set time (default 30 minutes). It may have crashed |
| Priority | The dashboard's sort order (§4.3). A human wait that blocks the child ranks highest |
| Spinner | The rotating icon that marks a child as active (planning, working, or addressing changes) |
| Feed | One form of the timeline: events listed in time order |
| Swimlanes | One form of the timeline: one horizontal band per session, with state changes shown in color |

### Communication and mechanisms

| Term | Meaning |
|---|---|
| Push | A child sends to the hub on every change, and the hub forwards to the screen at once. The opposite of polling, where the receiver checks periodically |
| Polling | Checking for changes at a fixed interval. This tool uses polling for auxiliary features alone: `--watch-files`, `--pull-every`, and the fallback when the browser cannot use SSE |
| SSE (Server-Sent Events) | A mechanism by which a server keeps a connection open and sends a browser data as it comes. The dashboard uses SSE to update immediately |
| snapshot / update | The data sent over SSE: the whole state right after connecting (snapshot), then the changes (update) |
| outbox | A file on the child's side that holds events that did not reach the hub. The child resends them first on the next send |
| `HUB_URL` / `HUB_TOKEN` | The hub's Uniform Resource Locator (URL) and authentication token, used by children and the parent |
| `HUB_STORE` | The store directory. Without `HUB_URL`, a child also writes here directly |
| `HUB_SESSION_ID` | The current session's ID. If unset, the tool derives it from Claude Code's environment variables |
| Hook | A command Claude Code runs automatically at specific moments. This tool uses SessionStart, PostToolUse, and Stop |
| SessionStart hook | Runs at session start. It makes the command available and, if the session is unregistered, adds a short text to the context prompting registration |
| PostToolUse hook | Runs after a tool call. It sends task operations such as TodoWrite to the hub as progress |
| Stop hook | Runs at the end of a turn. It sends the heartbeat and, if the child is about to stop while still marked as working, asks it once to report |
| Skill | A set of instructions loaded when needed: `session-hub-report` for children, `session-hub-orchestrate` for the parent |
| `append_system_prompt` | Extra instructions that `create_session` keeps in force for a child. This tool passes the five-line reporting rules |
| `send_message` | Sends a message between sessions. Delivery runs the receiver's turn and therefore costs tokens. Used for escalation and instructions alone |
| `get_session` / `status_bucket` | The call that fetches a session's state, and that state in coarse form (working / blocked / failed and so on). Used to confirm a stall |
| `list_events` | The call that reads a child's transcript. Heavy, so avoided as a rule |

### Knowledge and collections

| Term | Meaning |
|---|---|
| Collection | A definition of which received updates to collect (match), how to combine them (reduce), how to show them (view), and where else to write them (sinks) — together with the result. A projection of the event store |
| Projection | Data computed from the stored event sequence in a shape that fits a purpose. The original events stay unchanged |
| match | The condition for an event to enter a collection |
| reduce | How to combine: log (keep the time series) / latest (the newest one per key) / aggregate (merge into one per key) |
| key | The unit that reduce treats as "the same item". For knowledge, the explicit key, or else the title (ignoring whitespace and case) |
| view | The display form: cards (grouped cards) / table |
| sink | An extra destination for a collection (a Markdown or JSONL file) |
| `collections.json` | The collection definitions at the root of the store. Used to add, override, or disable built-in collections |
| Knowledge | The built-in collection. It gathers in one place the findings and caveats that sub-sessions uncover while working |
| finding | The event type that enters knowledge, sent with `session-hub learn` |
| kind (of a finding) | The type of finding: caveat / issue (open issue) / decision / howto (how-to) / insight |
| scope | Where a finding applies (a path, module, or service name). `knowledge --scope` uses it to read only the relevant findings |
| obsolete | A finding that no longer holds. It leaves the display and the `knowledge` output, but its history remains |
| Reporters | The sessions that reported an item. The more reporters, the more workers hit the same thing |
