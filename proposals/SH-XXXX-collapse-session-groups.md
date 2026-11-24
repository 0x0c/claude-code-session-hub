**English** · [日本語](SH-XXXX-collapse-session-groups.ja.md)

# SH-XXXX — Collapse the session list by status

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#19](https://github.com/0x0c/claude-code-session-hub/pull/19) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We make each status group in the dashboard's session list collapsible. The list has three groups:
"Needs action", "Working and waiting", and "Done". A click on a group heading hides or shows the
cards of that group, and the browser remembers the choice.

## Motivation

The session list shows every card of every group. Finished sessions accumulate, and each card takes
several lines. A user who follows many sessions must scroll past cards that need no attention.

Once the change ships, a user can collapse "Done" with one click. The group then occupies one line
with its count, and it stays collapsed after a live update and after a page reload.

## Detailed design

The change touches `session_hub/templates/dashboard.html` alone.

- **Heading.** Each group heading becomes a button inside a level-three heading. The button carries
  `aria-expanded`, shows a ▾ or ▸ marker, and keeps the session count in both states. The existing
  group labels name the button, so the `MESSAGES` table needs no new label.
- **State.** Every group starts expanded. The ids of the collapsed groups (`action`, `active`, and
  `done`) live in `localStorage` under `hub.collapsed`. The page works without storage; the choice
  then lasts until a reload.
- **Hidden activity.** A collapsed heading glows when one of its hidden sessions sends a message. It
  also shows the selection mark when the selected session is hidden.
- **Moves between groups.** A session that changes group follows the state of its new group. A
  collapsed group never expands by itself, because the user chose to collapse it.
- **Focus.** Every update rebuilds the list, so the page returns the keyboard focus to the heading
  that held it.

The header count, the tab title, and the browser notifications ignore the collapsed state. A
session that needs action therefore stays visible in the header even when its group is collapsed.

## Alternatives considered

- **One group per state.** The thirteen or so badge states would split the list into many short
  groups and lose the "attention first" order. The three existing groups already answer who must act.
- **The HyperText Markup Language (HTML) `details` element.** Every update rebuilds the list, so the
  page must track the open state in any case, and the element would add a second copy of that state.
- **Collapse "Done" by default.** A first-time user could think that finished sessions vanished.

## Progress

- [x] Design approved
- [x] Implementation checked in a browser (the test suite has no browser harness)
- [x] Documentation updated (docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../session_hub/templates/dashboard.html) — `renderSessions()`.
- [`docs/DESIGN.md`](../docs/DESIGN.md) §5.2 — the screen layout.
