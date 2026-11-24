**English** · [日本語](SH-0024-session-overview.ja.md)

# SH-0024 — Overview of every session's lifespan

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0024 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#36](https://github.com/0x0c/claude-code-session-hub/pull/36) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We add an Overview tab to the dashboard's timeline. It draws one thin band per session over the whole
history, in state colors alone, so that every session fits one screen. The tab replaces the grid
layout's *All sessions* button, which we remove.

## Motivation

The timeline already traces every session in a feed and in swimlanes, but neither gives a quick
look at all of them. The swimlanes give each session a tall lane with event dots, and a user who runs
many sessions over several days scrolls to see them. The grid layout reached the all-session
timeline only through a button that opened the same panel without a limit.

Once the change ships, a user can open the Overview tab and see, on one screen, when each session ran
and where it waited for a human or stalled.

## Detailed design

The change touches the dashboard page, its playbook, and the design document. It adds no event and no
server request.

- **Tab.** The timeline gains a third tab, *Overview* (俯瞰), beside *Feed* and *Swimlanes*.
- **Axis.** All bands share one axis from the oldest event to the present. Percentages place the
  bands; a resize redraws the tab so that the labels fit. The labels between the start of the history and "now" fall
  on round local times, at most six of them, and fewer in a narrow panel so that they do not touch.
- **Bands.** One band per session, in the session list's order, ignoring the session filter so that
  the tab always shows every session. The search and event filters are hidden in this tab. The state runs come from `laneSegments()`, the function that the
  swimlanes use. Hovering a run shows its state and period. The band has no dots, zoom, or table.
- **Selection.** Clicking a session's name selects the session, as in the swimlanes, and marks its
  row. In the grid layout the panel stays open.
- **Removed.** The *All sessions* button, its labels, and its handler go. The grid panel opens from a
  card, and the Overview tab shows every session from there. When the panel closes and its card is gone,
  the focus moves to the *Grid* button. The grid no longer offers the unfiltered feed by itself; the
  session filter in the panel still does.
- **Labels.** Every label has an English and a Japanese entry in `MESSAGES`.

## Alternatives considered

- **A third layout beside the list and the grid.** It moves the overview out of the timeline panel,
  but it adds a layout to every grid rule (panel, scrolling, focus) for a read-only picture.
- **A zoom-out mode of the swimlanes.** It keeps one view, but a lane that is tall enough for dots
  cannot fit many sessions, and a mode that hides the dots confuses the controls.
- **A command-line overview.** `session-hub log` already follows events in a terminal; a picture of
  durations needs the dashboard.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md, README screenshots in docs/images/)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) —
  `renderOverview()` and `laneSegments()`.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
