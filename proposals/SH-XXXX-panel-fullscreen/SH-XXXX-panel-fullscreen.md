**English** · [日本語](SH-XXXX-panel-fullscreen.ja.md)

# SH-XXXX — Fullscreen mode for the detail panel

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#41](https://github.com/0x0c/claude-code-session-hub/pull/41) |
| Related | [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md), [SH-0017](../SH-0017-grid-panel-resize/SH-0017-grid-panel-resize.md) |
<!-- /SH-METADATA -->

## Introduction

The detail panel of the dashboard's grid layout gains a fullscreen mode. A button in the panel's title
expands the panel over the whole browser window, and the same button or Escape brings the previous
width back.

## Motivation

The grid layout shows a session's timeline in a panel on the right, next to the session cards. The
panel takes at most 720 pixels and 55% of the window. Swimlanes, the tables of collections, and long
messages do not fit that width well. A viewer who wants the whole window for one session has no way to
get it without leaving the grid layout.

Once the change ships, one click draws the swimlanes of a 1440-pixel-wide window over the full 1440
pixels, and one press of Escape returns to the cards and the same panel.

## Detailed design

### Entering and leaving

The panel's title gains the button `#fullscreenPanel` between **Delete session** and the close button.
The grid layout alone shows the button. The mode belongs to the open panel, and the browser does not
remember it.

| Action | Result |
|---|---|
| Press the button | The panel covers the window, over the page header and the cards |
| Press the button again | The panel takes its previous width |
| Press Escape | In a non-empty search field, clears the field; otherwise leaves fullscreen; otherwise closes the panel |
| Hold Escape | Leaves fullscreen and stops; the key's repeats do not close the panel |
| Close the panel, or delete the selected session | Leaves fullscreen and closes the panel |
| The selected session disappears | Leaves fullscreen and closes the panel |
| The layout changes to the list | Leaves fullscreen |

### Geometry

`main` carries the class `fullscreen`, and one Cascading Style Sheets (CSS) rule overrides the panel's
position and width. The rule leaves `--detail-w`, the width of the panel beside the cards, unchanged,
so removing the class restores that width whatever set it. The panel lies above the header and below
the swimlanes' tooltip. The browser draws its own confirmation dialogs above the page.

The switch is immediate. An animated width would reflow the timeline on every frame, and an immediate
switch needs no exception for the reduced-motion setting (`prefers-reduced-motion`). The page behind
the panel does not scroll while the mode lasts.

A window at most 860 pixels wide offers the button too. There the panel already fills the width, and
fullscreen adds the height of the page header, which is largest in a narrow window because the header
wraps.

### Content

- The panel keeps the first visible row at the same distance below its title, because the new width
  changes the height of the rows above. At the end of the content, the scroll range limits this
  correction.
- The swimlanes redraw to the new width.
- Live updates do not touch the mode; the bar that announces new events and the sticky title work as
  they do in the normal panel.
- The line between the selected card and the panel belongs to the list layout, so fullscreen never
  shows it.

### Accessibility

The button has the constant name "Fullscreen" and reports its state in `aria-pressed`; the tooltip
names the next action. The page header and the session list become inert, so neither the Tab key nor a
screen reader reaches what the panel covers. The connection indicator in the header is therefore
silent until the mode ends. The focus stays where it was inside the panel, or moves to the button when
it was outside. Closing the panel returns the focus to the card, as before.

### Scope

The change touches `session_hub/templates/dashboard.html`, and the playbook gains a story for the
button. The labels live in the `MESSAGES` table in English and Japanese. Events, the store, and the
endpoints stay unchanged.

## Alternatives considered

- **The browser's Fullscreen application programming interface (API).** It takes over the whole screen, shows a browser notice on each
  entry, needs a user gesture, and is missing for page elements in Safari on the iPhone. The browser
  also consumes Escape itself, which would prevent the search field from using the key first. A CSS
  class fills the window the viewer already sized and leaves the key to the page.
- **A modal dialog element.** Moving the panel into a `<dialog>` would change the element that the
  list layout shares. Inert neighbors give the same protection with the panel in place.
- **Remember the mode.** A fullscreen panel hides every other session. A viewer should choose that
  state for the session at hand rather than meet it on the next click on a card.
- **Hide the button in a narrow window.** The header costs the most height exactly there.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md) — the grid and its detail panel.
- [SH-0017](../SH-0017-grid-panel-resize/SH-0017-grid-panel-resize.md) — the panel's width beside the cards.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
