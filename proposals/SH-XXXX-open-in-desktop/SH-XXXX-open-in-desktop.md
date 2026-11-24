**English** · [日本語](SH-XXXX-open-in-desktop.ja.md)

# SH-XXXX — Open a session in the Claude desktop app

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#42](https://github.com/0x0c/claude-code-session-hub/pull/42) |
| Related | [SH-0011](../SH-0011-session-archive/SH-0011-session-archive.md), [SH-0019](../SH-0019-detail-pr-link/SH-0019-detail-pr-link.md) |
<!-- /SH-METADATA -->

## Introduction

The detail panel of the dashboard links to the selected session in the Claude desktop app. One click
moves the reader from the session's history to the conversation itself.

## Motivation

The dashboard tells the reader that a session needs an answer, but the answer belongs in the session.
A reader who runs sessions in the Claude desktop app must find the same session again in the app's
sidebar, by its name.

Once the change ships, selecting a session of the desktop app shows **Open in Claude** in the panel's
title. A click brings the app to the front with that session open.

## Detailed design

The app registers the Uniform Resource Locator (URL) scheme `claude`. We verified on macOS, with version 6.28899.6, that
`claude://code/continue?session=local_<id>` opens the named session. The app's code shows the Code tab's
home when the id is unknown or names an archived session, so a stale link does no harm.

- **Id.** The app's id differs from the hub's session id. The hub already scans the app's session
  files, `local_*.json`, every five seconds. The scan reads two more fields:
  - `sessionId` holds the app's id. The scan accepts the form `local_` plus 1 to 64 letters, digits,
    or hyphens.
  - `lastActivityAt` orders the app's sessions by time.
- **Several app sessions.** When several unarchived app sessions share one hub session, the link opens
  the one with the latest `lastActivityAt`.
- **Snapshot.** The hub adds the app's id to each session of the snapshot as `desktop_id`. A session
  has no `desktop_id` when the app does not know it, or when every app session behind it is archived.
  A change to an id pushes an update to every open page.
- **Page.** The link stands in the panel's title after the link to the pull request (PR), in both
  layouts. The link is hidden when no session is selected or the session has no `desktop_id`.
- **Safety.** The page checks the form of the id again and builds the URL itself. Neither a pushed
  message nor a file can supply a whole URL.
- **Store.** The hub writes no event for the id. The id is a fact about this machine that the app's
  files always answer, and a shared store would carry the id to machines where it opens nothing. `session-hub export`
  removes the id from a snapshot that it reads from a running hub, so a static export has no link.
- **Compatibility.** `desktop_id` is a new, optional field of the snapshot. Events, the status record,
  and stored files stay as they are. `HUB_DESKTOP_SESSIONS=0` turns the link off together with the
  detection of archived sessions.

The scheme is undocumented, so a later version of the app may change it. The link then opens the app
elsewhere or does nothing, and the rest of the dashboard is unaffected. A browser may ask for a
confirmation before it opens the app.

The change adds no text to any hook, skill, or default command output. `session-hub status --json`
prints the snapshot's sessions as they are, so its output gains the `desktop_id` field when it reads a
running hub.

## Alternatives considered

- **`claude://claude.ai/epitaxy/local_<id>`.** The form opens the session too. The path is the page's
  internal route, whereas `code/continue` names an entry point with a fallback.
- **`claude://resume?session=<hub session id>`.** The form needs no lookup. The app handles it by
  importing a session of the command-line interface (CLI), which is more than opening a session.
- **An endpoint that runs `open` on the hub's machine.** A link lets the browser ask the reader first,
  and the hub gains no endpoint that starts programs.
- **A link on each card.** The card already opens the detail panel, and a second link there crowds a
  small card.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/desktop.py`](../../session_hub/desktop.py) — the scan of the app's session files.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the page.
- [SH-0011](../SH-0011-session-archive/SH-0011-session-archive.md) — the scan's first use.
- [SH-0019](../SH-0019-detail-pr-link/SH-0019-detail-pr-link.md) — the PR link in the panel's title.
