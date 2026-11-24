**English** · [日本語](SH-0028-archived-by-project.ja.md)

# SH-0028 — Group archived sessions by project

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0028 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#43](https://github.com/0x0c/claude-code-session-hub/pull/43) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

In the grouping by project, the dashboard splits the **Archived** group by project. Each project group
is collapsible on its own.

## Motivation

The **Archived** group lists its sessions by last update alone. Sessions of different projects mix, and
the group grows with every archived session, so finding the past work of one project means reading
every card.

Once the change ships, a user who opens **Archived** sees the archived sessions of each project
together, and can collapse a project with one click.

## Detailed design

The change touches the session list in `session_hub/templates/dashboard.html`. It adds one story to
`session_hub/templates/playbook.js`.

- **Groups.** When **By project** is on, the Archived group holds one group per project (`repo`). The
  project with the newest update comes first, and sessions without a project come last under
  "No project". Each group keeps the order by last update.
- **Grouping by status.** When **By project** is off, the Archived group stays a flat list.
- **Position.** The Archived group stays at the bottom of the list and starts collapsed.
- **Heading.** A project heading inside Archived uses the indented heading style of the status groups
  inside a project. The heading shows the project's name and count, without a badge or a help icon. The labels exist
  already, so the `MESSAGES` table needs no new label.
- **Cards.** A card inside a project group omits the project's name, which the heading shows.
- **State.** Every project group inside Archived starts expanded. The browser stores a collapsed one in
  `hub.collapsed` under the JavaScript Object Notation (JSON) array of project and status, such as
  `["acme/app","archived"]`. Collapsing a project inside Archived therefore leaves the project's
  section above unchanged.
- **Hidden activity.** The outermost collapsed heading carries the glow and the selection mark of its
  hidden sessions.
- **Focus.** When a focused session moves into a collapsed group, the focus goes to the outermost
  collapsed heading. When a focused project group empties, the focus goes to the Archived heading.

## Alternatives considered

- **Move the archived sessions into each project's section.** A project whose sessions are all archived
  would keep a section in the list, although archiving removes sessions from view.
- **Group by project in the grouping by status too.** Turning **By project** off asks for no project
  headings, so the Archived group follows the same choice.
- **Start every project group collapsed.** Opening Archived would then take a second click to show any
  session.

## Progress

- [x] Design approved
- [x] Implementation checked in a browser (the test suite has no browser harness)
- [x] Documentation updated (README.md, docs/DESIGN.md)
- [x] README screenshots regenerated

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `subGroups()` and `rebuildSessions()`.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
