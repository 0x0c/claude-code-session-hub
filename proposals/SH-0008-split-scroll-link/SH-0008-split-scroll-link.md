**English** · [日本語](SH-0008-split-scroll-link.ja.md)

# SH-0008 — Scroll the panels apart and link the selection

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0008 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#17](https://github.com/0x0c/claude-code-session-hub/pull/17) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

On a desktop window, the dashboard's session list and its detail panel scroll independently. When
the viewer selects a session, a connector line runs from that session's card to the detail panel.
The viewer can browse a long list without losing the place in a timeline, and the line shows which
session the detail belongs to.

## Motivation

Both panels share the page's scroll position today. Reading down a long timeline carries the session
list off screen, so selecting another session means scrolling back to the top. The selected card has
a tinted background, but nothing visible ties that card to the detail panel on the other side of the
page.

Once the change ships, scrolling one panel leaves the other in place, the page itself does not
scroll, and the connector follows the selected card as the list scrolls.

## Detailed design

### The split layout

The layout applies to the list layout in a window wider than 860px and at least 480px tall. The page fills the window;
the header and both panels' titles stay fixed, as do the detail panel's filters. The session list
(`#sessions`) and a new wrapper around the detail views (`#detailScroll`) scroll on their own. Both accept
keyboard focus, so the arrow keys scroll them.

The grid layout is unchanged: its detail panel slides over the grid, scrolls as a whole, and has no
connector. A smaller window keeps the single page scroll. The phone layout stacks the panels, and a very short
window leaves too little height for two scrolling panels.

### Scroll position

- A re-render restores both scroll positions, because rebuilding the Document Object Model (DOM) can
  clamp them.
- Selecting another session, or switching the tab, returns the detail panel to its top.
- Selecting a session outside the list, such as in the filter, scrolls its card into view.
- The new-items bar follows the detail panel's scroll position in the split layout, and the page's
  otherwise.

### The connector

A Scalable Vector Graphics (SVG) overlay in `main` draws an elbow line through the gap between the
panels, with a dot at each end. The line starts at the selected card's right edge and ends at the
detail panel's left edge, level with the title. The detail panel's border takes the same accent
color. The overlay ignores pointer events.

- When the card is scrolled out of the list, the line starts at the nearest edge of the list and
  turns dashed.
- With no selection, or outside the split layout, the page draws no line.
- The line is redrawn after a render, a list scroll, a resize, and the periodic refresh of the
  relative times.

The overlay is decorative (`aria-hidden`). Each card also carries `aria-pressed`, which tells
assistive technology which session is selected.

## Alternatives considered

- **Make the list sticky.** A sticky list still needs its own scroll area once it outgrows the
  window, and the page scroll would keep moving the detail panel's title away from the line.
- **Match colors alone.** A shared color per session needs no drawing code, but a viewer must compare
  two distant areas, and similar hues are hard to tell apart.
- **Hide the line when its card is off screen.** The viewer would lose the direction in which to
  scroll back to the selected card.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the page.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) — the screen layout in §5.2.
