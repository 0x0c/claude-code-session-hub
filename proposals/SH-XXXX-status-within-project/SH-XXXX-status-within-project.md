**English** · [日本語](SH-XXXX-status-within-project.ja.md)

# SH-XXXX — Group sessions by status within a project

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#31](https://github.com/0x0c/claude-code-session-hub/pull/31) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

In the grouping by project, the dashboard splits each project into status groups: "Working and
waiting" and "Done". Each group is collapsible on its own.

## Motivation

A project section lists its sessions by last update alone, so finished sessions sit between working
ones. A user must choose between seeing the project and seeing the status, because the **By project**
button offers one grouping at a time.

Once the change ships, a user sees the working sessions of a project together above its finished
sessions, and can collapse the finished sessions of one project with one click.

## Detailed design

The change touches `session_hub/templates/dashboard.html` alone. Grouping by status stays the same.

- **Groups.** A project section holds "Working and waiting", then "Done". Each group keeps the order by
  last update. A group without sessions is not shown.
- **Sections outside the projects.** "Needs action" stays at the top of the list and "Archived" stays
  at the bottom, for the sessions of every project.
- **Heading.** A status heading is a project heading without the filled background. The heading shows
  the badge that the grouping by status uses for the group, and the group's count.
- **Alignment.** Project names, status badges, and the contents of the cards share one left edge. The
  arrows of the headings stand in a column to the left of the edge. In the grid layout, the frames of
  the cards start at the edge.
  The labels are the existing ones, so the `MESSAGES` table needs no new label.
- **State.** Every status group inside a project starts expanded. The browser stores a collapsed one in
  `hub.collapsed` under the JavaScript Object Notation (JSON) array of project and status, such as
  `["acme/app","done"]`. A choice in one project therefore affects no other project.
- **Hidden activity.** The heading of a collapsed group carries the glow and the selection mark of its
  hidden sessions. When the project is collapsed, the project heading carries them.
- **Focus.** When a focused session moves into a collapsed group, the focus goes to the outermost
  collapsed heading. When a focused status group empties, the focus goes to its project's heading.

The session filter keeps its options grouped by project alone.

## Alternatives considered

- **Move "Needs action" into each project.** A session that needs action could end up below the fold
  or inside a collapsed project, against the "attention first" order.
- **Move "Archived" into each project.** A project whose sessions are all archived would keep a section
  in the list, although archiving removes sessions from view.
- **A third mode next to the By project button.** The nested grouping shows everything the flat project
  grouping shows, so the flat one needs no mode of its own.
- **Project inside status.** The same project would appear under several headings.

## Progress

- [x] Design approved
- [x] Implementation checked in a browser (the test suite has no browser harness)
- [x] Documentation updated (README.md, docs/DESIGN.md)
- [x] README screenshots regenerated

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `rebuildSessions()`.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
