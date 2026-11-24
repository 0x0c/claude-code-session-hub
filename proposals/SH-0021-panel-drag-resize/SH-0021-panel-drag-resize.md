**English** · [日本語](SH-0021-panel-drag-resize.ja.md)

# SH-0021 — Drag to resize the detail panel

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0021 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#41](https://github.com/0x0c/claude-code-session-hub/pull/41) |
| Related | [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md), [SH-0017](../SH-0017-grid-panel-resize/SH-0017-grid-panel-resize.md) |
<!-- /SH-METADATA -->

## Introduction

The viewer can drag the left edge of the detail panel in the dashboard's grid layout to change the
panel's width. The cards reflow beside the panel during the drag, and the browser remembers the width.
[SH-0017](../SH-0017-grid-panel-resize/SH-0017-grid-panel-resize.md) made the cards share the window
with the open panel; this proposal lets the viewer choose the split.

## Motivation

The open panel takes the smaller of 720 pixels and 55% of the window, and nothing changes that split.
A viewer who compares many cards wants a narrow panel. A viewer who reads swimlanes or a long timeline
wants a wide one. On a 1920-pixel-wide window, the panel cannot grow past 720 pixels.

Once the change ships, a viewer with a 1920-pixel-wide window can widen the panel to about 1540 pixels
and narrow it to 360 pixels, and a reload keeps the chosen width.

## Detailed design

### The handle

A separator (`#panelResize`) lies on the panel's left edge, below the page header. The handle is a fixed
sibling of `#detail`, not a child, because `#detail` scrolls as a whole and would carry a child away.
Live updates re-render neither the handle nor its place.

| Input | Effect |
|---|---|
| Drag left or right | The panel widens or narrows and follows the pointer |
| Left or Right arrow | The panel widens or narrows by 24 pixels |
| Home or End | The panel takes its smallest or largest width |
| Double-click | The panel returns to the default width |
| Escape during a drag | The drag ends and the panel returns to its earlier width |

The drag uses pointer events with pointer capture, so a mouse and a finger work alike. A canceled
pointer restores the width from before the drag. A click without movement changes nothing.

The handle appears while the grid layout shows its panel beside the cards. The handle stays hidden
in the list layout, while the panel is closed, in a window at most 860 pixels wide, and while `main` has
the class `fullscreen`.

### The width and its bounds

The handle sets the custom property `--detail-w` on the root element. Both the panel's width and the
grid's right padding read that property, so the two always agree.

| Bound | Value | Reason |
|---|---|---|
| Smallest width | 360 pixels | The timeline stays readable |
| Largest width | The window's width minus 376 pixels | One 280-pixel card column and its padding fit beside the panel |

The page stores the preferred width in `localStorage` under `hub.panelWidth`, and works without storage.
A smaller window clamps the shown width and leaves the preference alone, so a larger window restores
the preferred width. A double-click removes the preference.

### What follows the width

The page applies at most one width per animation frame. Each change keeps one card in its vertical place, as
SH-0017 defines, and redraws the swimlanes, whose drawing depends on the panel's width. The slide
transition is off during a drag. The connector line belongs to the list layout and follows the panel
through the existing size observer.

### Accessibility

The handle is focusable and carries `role="separator"`, `aria-orientation="vertical"`, and
`aria-controls="detail"`. `aria-valuenow`, `aria-valuemin`, and `aria-valuemax` give the width in
pixels. Its name and tooltip are localized.

## Alternatives considered

- **The `resize` property of Cascading Style Sheets (CSS).** Browsers place its grip in a bottom corner, and it changes neither the
  grid's padding nor a stored preference.
- **A handle inside the panel.** An absolutely positioned child scrolls away with the panel's content.
- **A preference in percent.** A share of the window changes the panel's readable width with every
  window resize. A pixel width stays as the viewer set it.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md, README.md)

## References

- [SH-0005](../SH-0005-session-grid/SH-0005-session-grid.md) — the grid and its detail panel.
- [SH-0017](../SH-0017-grid-panel-resize/SH-0017-grid-panel-resize.md) — the grid beside the panel.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
