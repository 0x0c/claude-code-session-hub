**English** · [日本語](SH-XXXX-session-parent-links.ja.md)

# SH-XXXX — Show parent and child sessions in the session list

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#39](https://github.com/0x0c/claude-code-session-hub/pull/39) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

The session list shows which session started which. A sub-session sits indented under its parent's
card, tied to it by lines, when both belong to the same group of the list. Otherwise the sub-session's
card links to its parent. The hub also finds the parent by itself when the sub-session does not report it.

## Motivation

Every status already has a `parent_id` field, and no part of the dashboard shows it. A user who runs
several families of sessions sees one flat list and must remember who started whom.

The field is also incomplete, because `session-hub start --parent` is the one way to fill it. On the
author's hub, the Claude desktop app had started four sessions from other sessions, and one of the four
had no recorded parent.

Once the change ships, a user sees a sub-session that the desktop app started under its parent's card,
within seconds and without the sub-session naming its parent.

## Detailed design

### Find the parent

The hub takes the parent from three sources, the strongest first:

| Source (`parent_source`) | Where it comes from | Event field |
|---|---|---|
| `reported` | `session-hub start --parent <id>` | `parent_id` |
| `environment` | `HUB_PARENT_SESSION_ID`, sent by `start` and by the Stop hook | `parent_hint` |
| `desktop` | `spawnedFrom.sessionId` in the desktop app's session file | `parent_hint` of a `parent` event |

- **Folding.** The status holds `parent_id` and the new field `parent_source`. A weaker source never
  replaces a stronger one, whatever the order of arrival; within one source, the last value wins. A
  session that names itself gets no parent. A malformed `parent_hint` is dropped, because an automatic
  value must not make the hub refuse an update.
- **Environment.** `start` sends the hint for the running session alone, since the environment says
  nothing about another session.
- **Desktop app.** The hub reads `sessionId` and `spawnedFrom` in the scan it already makes every five
  seconds. It translates the app's ids to Claude Code session ids and records a `parent` event in
  `events/<session_id>@desktop.jsonl`. It records the event when the session has no parent and the
  hub knows the parent session. It records nothing when the app's files disagree.
- **Bookkeeping.** A `parent` event changes neither the state nor the heartbeat, and it neither creates
  nor unarchives a session. A store reader of an earlier version skips the unknown type.
- **Prompt.** `prompts/child-append-system-prompt.md` adds `--parent {{PARENT_SESSION_ID}}` to the start
  command, because a `claude -p` sub-session has no other source.

### Show the family

- **Same group.** In each list of cards, a session goes under its parent when the list holds both.
  Children are indented, and lines tie them to their parent, at any depth. A family takes the place of
  its most recently updated member; children follow the order by last update.
- **Different groups.** Groups keep their members, so a child that needs action stays at the top of the
  list. Its card shows "↳ <parent's title>". A click opens the collapsed groups that hide the parent,
  selects the parent, and scrolls to it.
- **Parent's card.** The card shows the number of its direct children in the hub, in any group.
- **Unknown parents and loops.** A parent that the hub does not know shows nothing. Sessions on a loop
  of parents stand alone, and their other descendants still go under them.
- **Grid layout.** A family stacks in one column of the grid. Cards in a list that holds a family keep
  their own height, since a stretched neighbor would be mostly empty.
- **Timeline.** A `parent` event appears as "Parent found" with the parent's title.

## Alternatives considered

- **Move every child under its parent, whatever its status.** A child that needs action would leave the
  top of the list and could hide inside a collapsed group.
- **Move finished children alone under their parent.** The heading "Working and waiting" would hold
  finished sessions.
- **Links alone, without indentation.** The change would be smaller, and a reader could not see the
  shape of a family.
- **Use the reported parent alone.** The sessions without a reported parent would stay flat.
- **Compute the app's parent when building the snapshot, without an event.** The event store would no
  longer be the single source of truth, and the link would vanish with the app's file.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, AGENTS.md, the child's system prompt)

## References

- [`session_hub/schema.py`](../../session_hub/schema.py) — `_apply_parent()`.
- [`session_hub/desktop.py`](../../session_hub/desktop.py) — the scan of the desktop app's files.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `families()`.
- [SH-0011](../SH-0011-session-archive/SH-0011-session-archive.md) — the first use of the app's files.
- [SH-0018](../SH-0018-status-within-project/SH-0018-status-within-project.md) — the groups of the list.
