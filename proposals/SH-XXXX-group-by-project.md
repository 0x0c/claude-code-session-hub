**English** · [日本語](SH-XXXX-group-by-project.ja.md)

# SH-XXXX — Group sessions by project

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

The dashboard groups its session list by project. Session Hub names the project of each session
automatically, from the Git remote or from the folder, and each project becomes a collapsible section
of the list. A button in the list's header switches back to grouping by status.

## Motivation

One hub serves every Claude Code session on the user's machine, so the session list mixes sessions
from unrelated repositories. A user who works on two repositories must recall, title by title, which
session belongs to which. The status schema already has a `repo` field, but nothing fills the field
unless a session passes `session-hub start --repo`, and the dashboard never shows it.

Once the change ships, a user with sessions in two repositories sees two sections, each headed by the
repository name, without changing any setting or prompt.

## Detailed design

### Naming the project

`session_hub/project.py` names the project of a folder. The first rule that yields a name wins:

1. The path of the `origin` remote, without the host, the credentials, and the `.git` suffix:
   `acme/app`. A remote that is a local path yields its last folder.
2. The folder that holds the Git repository. A worktree yields the folder of its main checkout.
3. The name of the folder itself, for a project without Git.

The folder is `CLAUDE_PROJECT_DIR` when it is set, and the working directory otherwise. Each Git call
has a two-second limit, and a failure falls through to the next rule.

### Reporting the project

The name travels in the existing `repo` field, so the event format stays the same. The server clips
`repo` to 120 characters.

- The SessionStart hook keeps the name in the session's local state and sends nothing.
- `session-hub start` sends `--repo` when it is given, then the kept name, then a detected name. It
  detects nothing for another session's id (`--session`), because the caller's folder says nothing
  about that session.
- The Stop hook adds `repo` to the heartbeat it already sends. A session that started before the
  upgrade therefore joins its project at the end of its next turn.

A heartbeat fills `repo` when the status has none and never replaces a reported name. An explicit
`--repo` also replaces the kept name, so a later `start` without the option repeats the explicit
choice. A `start` on a machine that did not keep the explicit choice sends the detected name, which
replaces it. The change adds no text to any model's context.

### Dashboard

- **Order.** Sessions keep the server's urgency order inside a section. The section that holds the
  most urgent session comes first, and sessions without a project come last under "No project".
- **Header.** A section header shows the project, the number of sessions that need action, and the
  number of sessions. A click collapses or expands the section.
- **Collapsed sections.** The header of a collapsed section carries the glow of a received message.
- **Switch.** The **By project** button toggles between grouping by project and by status, and the
  page starts with grouping by project. In the status grouping, each card shows its project.
- **Session filter.** The session selector groups its options by project in the same way.
- **Persistence.** The browser keeps the grouping and the collapsed sections in `localStorage`.

Swimlanes, collections, and the command-line interface (CLI) output stay the same.

## Alternatives considered

- **Ask each session to pass `--repo`.** The skill text would cost tokens in every session, and a
  session that forgets the option would stay ungrouped.
- **Detect the project on the server.** The server sees neither the session's folder nor its Git
  configuration.
- **Add a `project` field next to `repo`.** Two fields would name the same grouping. `--repo` already
  accepts any name.
- **Group by the full path.** Two worktrees of one repository would fall into two groups.
- **Keep grouping by status as the default.** Status badges, the header count, and the urgency order
  already show what needs action, while nothing else shows the project.

## Progress

- [ ] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)
- [x] README screenshots regenerated

## References

- [`session_hub/hooks.py`](../session_hub/hooks.py) — the SessionStart and Stop hooks.
- [`session_hub/schema.py`](../session_hub/schema.py) — the `repo` field.
- [`session_hub/templates/dashboard.html`](../session_hub/templates/dashboard.html) — the session list.
- [`docs/DESIGN.md`](../docs/DESIGN.md) §1.1 — the status fields.
