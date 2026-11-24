**English** · [日本語](SH-XXXX-feed-project-name.ja.md)

# SH-XXXX — Name the project in feed rows

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Dashboard |
| Implementing PR | — |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

Each row of the feed names the project of its session beside the session name, and the search finds
rows by that name.

## Motivation

The feed mixes the events of every session. Sessions of different projects can have similar names,
and a row alone does not tell which project it belongs to.

Once the change ships, a user can read the project from each row, and can type a project name into
the search to see the events of that project alone.

## Detailed design

The change touches the dashboard page, its playbook, and the design document.

- **Source.** The name is the `repo` of the session, which the cards and the project groups already
  use. The event itself does not change.
- **Row.** The name follows the session name in muted text. A row whose session has no project shows
  no name, and a long name wraps. Collapsed heartbeats stay as they are.
- **Search.** The search also matches the project name. The table of the swimlanes uses the same
  filter, so the search finds the project there too.

## Alternatives considered

- **A project filter beside the session filter.** It adds a control, and it does not tell the project
  of a row while every project is shown.
- **The project inside the session name.** It repeats the project in the card and in every list of
  sessions, which already show it.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md, README screenshots in docs/images/)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `eventRow()` and
  `filteredEvents()`.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
