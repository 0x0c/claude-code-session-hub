**English** · [日本語](SH-0011-session-archive.ja.md)

# SH-0011 — Reflect archived sessions

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0011 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Hub server |
| Implementing PR | [#24](https://github.com/0x0c/claude-code-session-hub/pull/24) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

Session Hub learns that a session was archived and shows the fact as part of the session's status.
When a user archives a session in the Claude desktop app, the hub records an `archive` event. The
dashboard then moves the session into an **Archived** group, and the session no longer asks for
attention. Unarchiving the session in the app brings back its previous status.

For a session that the app does not manage, the commands `session-hub archive <session_id>` and
`session-hub unarchive <session_id>` record the same events.

## Motivation

The hub knows what a session reports about itself, and an archived session reports nothing. A user
who archives a working session in the app sees it turn into "Stale?" on the dashboard 30 minutes
later. A session archived while it waited for an answer stays under "Needs action" forever. Both
appear in `session-hub attention`, where they cost the parent tokens and prompt it to chase a session
that nobody wants to continue. The existing remedy, deletion, throws away the history as well.

Once the change ships, a user who archives a session in the app sees it move to the **Archived** group
of every open dashboard within about ten seconds, and `session-hub attention` stops listing it. After
the user unarchives the session, its question or its last state is back.

## Detailed design

### Events and status

Two event types join the protocol: `archive` and `unarchive`. The folded status gains one field,
`archived`, which is `null` or `{"since": <timestamp>, "by": <writer>}`.

- Archiving is a flag beside `state`, so `done`, `failed`, or an open question stays visible.
- Neither event changes `heartbeat` or `updated_at`, because archiving is not activity of the session.
- A second `archive` event on an archived session changes nothing.
- A child's report clears the flag of a session archived by hand, because a hidden question would be
  lost. Heartbeats and hook reports do not clear the flag. A child's report never clears a flag that
  the app set; the app alone decides when such a session comes back.
- While the flag is set, no event prints a `[HUB/1]` line for the parent. A question that a child asks
  after the app archived its session stays recorded, and appears once the user unarchives the session.

The view treats an archived session as neither stale nor in need of action, and sorts it last. An
earlier version of the hub skips lines with the new event types and shows such a session as before.

### Detecting an archive in the desktop app

The desktop app keeps one JavaScript Object Notation (JSON) file per session under
`~/Library/Application Support/Claude/claude-code-sessions/<account>/<organization>/local_<id>.json`.
Two fields matter. `cliSessionId` is the Claude Code session identifier (ID), which is also the hub's
session ID. `isArchived` is the archive flag.

A session that holds archive events alone, because its own file was deleted, does not appear.

`session_hub/desktop.py` reads these files and never writes to the directory. `Hub.run()` scans them
every five seconds and parses a file again only after its size or modification time changes. For each
session in the hub's store, `Hub.sync_desktop()` compares the flag with the status:

| App | Status | Recorded event |
|---|---|---|
| archived | not archived | `archive` |
| not archived | archived by `desktop` | `unarchive` |
| not archived | archived by another writer | none |
| no file, or an unreadable file | any | none |

The events go to `<session_id>@desktop.jsonl`, a file that the hub alone writes. The hub decides from a
fresh read of the store, so a session deleted in the meantime does not reappear. When several app
sessions share one `cliSessionId`, the session counts as archived only if all of them are. The
format of the files is undocumented, so the hub ignores a file it does not understand, and an error never stops its periodic
work.

`HUB_DESKTOP_SESSIONS` overrides the directory; `0` or an empty value turns the scan off. The default
directory exists on macOS alone, so other systems scan nothing unless the variable is set.

### Commands

`session-hub archive <session_id>` and `session-hub unarchive <session_id>` record the event as the
writer `parent`, and exit with status 1 when the session does not exist. While the app shows a session
as archived, a manual `unarchive` lasts until the next scan. `session-hub status` prints the code `AR`.

### Dashboard

A collapsed **Archived** group follows the other groups, whether the list groups sessions by state or
by project, and holds the archived sessions of every project. Each card in the group shows the **Archived**
badge next to the label of the preserved state, and hides an open question. In the swimlanes, the
lane of an archived session that is not `done`, `abandoned`, or `failed` ends at the archive time.

## Alternatives considered

- **An `archived` state.** It would overwrite `done` or `failed`, and unarchiving would have to remember
  the previous state elsewhere.
- **Manual commands alone.** Users archive in the app; a second, manual step would be forgotten.
- **A Claude Code hook.** A SessionEnd hook runs when a process exits, which also happens without an
  archive, and an idle session has no process that could run a hook at archive time.
- **Deleting the session from the hub.** Deletion loses the history and cannot be undone.
- **Watching cloud sessions.** Their archive flag needs a remote request with credentials. The
  commands cover these sessions.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, AGENTS.md)

## References

- [`session_hub/desktop.py`](../../session_hub/desktop.py) — reads the app's session files.
- [`session_hub/schema.py`](../../session_hub/schema.py) — the event types and the fold.
- [`session_hub/server.py`](../../session_hub/server.py) — `Hub.sync_desktop()`.
- [SH-0002](../SH-0002-delete-session/SH-0002-delete-session.md) — deleting a session.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §3.1 — event sourcing and the one-file-per-writer layout.
