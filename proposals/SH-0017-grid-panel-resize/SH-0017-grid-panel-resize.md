**English** · [日本語](SH-0017-grid-panel-resize.ja.md)

# SH-0017 — Resize the grid beside the detail panel

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0017 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#32](https://github.com/0x0c/claude-code-session-hub/pull/32) |
| Related | [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md) |
<!-- /SH-METADATA -->

## Introduction

In the dashboard's grid layout, the session cards narrow to the space beside the detail panel while the
panel is open, so the panel no longer covers any card. This proposal replaces the overlay that
[SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md) chose for the detail panel.

## Motivation

The grid layout spreads the session cards over the window, and a click on a card opens a detail panel
on the right. That panel lies over the grid and hides up to 720 pixels of cards. A viewer must close
the panel to see or select a covered session.

Once the change ships, every card in a 1280-pixel-wide window stays fully to the left of the open panel.

## Detailed design

### Widths

| Window width | Open panel | Grid |
|---|---|---|
| More than 860 pixels | The smaller of 720 pixels and 55% of the window | The remaining width; the cards reflow into fewer columns |
| At most 860 pixels | The full width below the page header | Covered by the panel until it closes |

The panel still slides in over 0.2 seconds. The grid takes its new width at once, because animating
the width would reflow every card on every frame. When the panel closes, the grid takes the full
width again.

### Scroll position

A reflow moves the cards. The page therefore scrolls the window so that one card keeps its vertical
place: the selected card, or else the first visible card when the window is scrolled. Near the top or
the bottom of the page, the scroll range limits this correction.

### Scope

The change touches `session_hub/templates/dashboard.html`. Selection, keyboard focus, and the closed
panel's inert state stay as SH-0005 defines them.

## Alternatives considered

- **Keep the overlay.** SH-0005 chose the overlay because a reflow moves the card under the pointer.
  Hidden cards cost more than moving cards, and the scroll correction keeps the vertical movement small.
- **Share a small window as well.** Below 860 pixels, neither the cards nor the timeline would have a
  readable width.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md)

## References

- [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md) — the grid and its detail panel.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
