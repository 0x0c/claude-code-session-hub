**English** · [日本語](SH-0001-delete-session.ja.md)

# SH-0001 — Delete a session's messages

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0001 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Hub server |
| Implementing PR | [#3](https://github.com/0x0c/claude-code-session-hub/pull/3) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We add a way to delete every stored message of one sub-session. A user removes a session from the
dashboard with a **Delete session** button, or from a terminal with `session-hub delete
<session_id>`. The hub physically removes the session's event files from the store, rebuilds its
snapshot, and tells every open dashboard to drop the session at once.

The store keeps its current format: append-only JavaScript Object Notation (JSON) Lines files, one
file per writer. Deletion is the single, explicit exception to "append-only", and it works on whole
sessions alone, so the remaining events of every other session stay untouched.

## Motivation

The hub already persists every message it receives. Each message is one line in
`<store>/events/<session_id>.jsonl`, and the hub rebuilds its state from those files after a
restart. Nothing ever removes a line, so finished, failed, and test sessions pile up forever:

- The session list grows until the sessions that need action drown among old ones.
- Demo and experiment sessions stay mixed with real work.
- The only way to clean up today is to stop the hub and delete files by hand, which needs knowledge
  of the store layout and of the parent's `@parent` files.

Once the change ships, a user who clicks **Delete session** on a finished session sees that session
disappear from the session list, the timeline, and every collection within a second, in every open
dashboard. Its files are gone from `<store>/events/`, and the session does not come back after the
hub restarts.

## Detailed design

### Store

`EventStore.delete_session(session_id) -> int` deletes every file of the session and returns the
number of events those files held:

1. Validate `session_id` with the same check as `append` (`SAFE_ID`, no `@`).
2. Collect the session's files: `<session_id>.jsonl` and every `<session_id>@<writer>.jsonl`.
3. For each file, take the exclusive file lock that `append` uses, count its valid events, and
   unlink the file while still holding the lock.
4. Return the total count. A count of `0` means the store held no such session.

Deletion races with a writer in one way. A writer may open a file, then wait for the lock while
`delete_session` unlinks the file; the writer would then append to a file that no longer has a name,
and its event would vanish. To close that gap, `append` checks after it takes the lock whether the
open file still has a name (`os.fstat(...).st_nlink > 0`). When the name is gone, `append` reopens the
path, which creates a fresh file. A session that keeps reporting after a deletion therefore reappears
with its new events alone, and no event is lost silently.

### Hub server

`Hub.delete_session(session_id) -> int` calls the store method under the hub's write lock, then calls
`publish()`. `publish()` already compares the new snapshot with the previous one and broadcasts the
ids of vanished events in the `removed` field of the `update` message, together with the new session
list and collections. The collection sinks are rewritten as after any other change.

A new endpoint exposes the operation:

```
DELETE /api/sessions/<session_id>
  200 {"session_id": "...", "deleted": <event count>}
  400 {"error": "..."}            invalid session id
  401 {"error": "unauthorized"}   same token rule as the other endpoints
  404 {"error": "no such session"}
```

We choose the `DELETE` method on purpose. A web page from another origin cannot send a cross-origin
`DELETE` without a Cross-Origin Resource Sharing (CORS) preflight request, and the hub answers no
preflight. A malicious page that the user happens to open therefore cannot delete sessions through
the loopback hub, while a `POST` with a simple content type could reach it.

### Command-line interface (CLI)

`session-hub delete <session_id>` deletes one session and prints `deleted <session_id> (<n> events)`.
It picks the route the same way the reporting commands do:

1. When `HUB_URL` is set and `--store` is not given, send `DELETE /api/sessions/<session_id>` to the
   hub, so the dashboards update at once.
2. When the hub is unreachable and a store is configured (`HUB_STORE` or `--store`), delete from the
   store directly. The hub picks the change up on its next rebuild (the next message, or the
   30-second recheck).
3. Without `HUB_URL`, delete from the store directly.

After a direct deletion in a Git-backed store, the command runs the existing `sync`, which stages the
removed files (`git add events` stages deletions) and pushes them. The command exits with status 1
when the session does not exist. It asks no confirmation question, because agents and scripts run
the command-line interface (CLI) non-interactively; the explicit session id is the confirmation.

### Dashboard

When a session is selected and the page is live (not a static export from `session-hub export`), the timeline header shows a **Delete session** button at its right end. The button sits in
the header rather than on each session card because a card is itself a button, and a nested button
is not accessible.

1. A click opens a confirmation dialog that names the session and the number of its messages, and
   states that the deletion cannot be undone.
2. On confirmation, the page sends `DELETE api/sessions/<session_id>` and clears the selection.
3. The `update` message that follows removes the session's events, card, and collection entries.
4. On a failure, the page shows the server's error in an alert and keeps everything.

The polling fallback (used when Server-Sent Events (SSE) fail) also learns about removals: it
computes the ids of events missing from the new snapshot and passes them as `removed`. Both labels
and the dialog text live in the `MESSAGES` table in English and Japanese.

### What stays the same

- The event format, the file layout, and every existing endpoint stay unchanged, so an older hub or
  CLI reads a store that went through a deletion without trouble.
- Single-event deletion and logical deletion (a "deleted" marker event) are out of scope.
- The shipped skills do not mention the command. Deletion is a human's housekeeping decision, not a
  step of the parent's routine, and a line in a skill costs tokens on every load.

## Alternatives considered

- **Move the store to SQLite.** SQLite makes deletion a single statement and scales better, but one
  binary file breaks sharing the store through Git, which relies on one append-only text file per
  writer. Deletion does not need a database, so we keep the files.
- **Logical deletion with a marker event.** Appending a `deleted` event keeps the store
  append-only, but the data stays on disk and every reader must learn to skip it. The user asked for
  the data to be gone.
- **Delete single messages.** Removing one event would change the folded state of a session in
  surprising ways (an answer without its question, for example) and needs rewriting a file in place.
  Whole-session deletion covers the housekeeping need without that risk.
- **A delete button on each session card.** The card is already a button that selects the session;
  a nested button would break keyboard and screen-reader use.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/store.py`](../session_hub/store.py) — the event store and its per-writer files.
- [`session_hub/server.py`](../session_hub/server.py) — `Hub.publish()` and the `removed` field.
- [`session_hub/templates/dashboard.html`](../session_hub/templates/dashboard.html) — the dashboard.
- [`docs/DESIGN.md`](../docs/DESIGN.md) §3.1 — event sourcing and the one-file-per-writer layout.
