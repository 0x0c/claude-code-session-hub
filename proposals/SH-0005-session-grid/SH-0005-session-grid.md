**English** · [日本語](SH-0005-session-grid.ja.md)

# SH-0005 — Session grid with a detail panel

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0005 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#15](https://github.com/0x0c/claude-code-session-hub/pull/15) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We add a grid layout to the dashboard. The grid spreads the session cards over the full width of the
window. A click on a card slides a detail panel in from the right, and the panel shows that session's
timeline. A toggle in the session list's header switches between the existing list layout and the
grid, and the browser remembers the choice.

## Motivation

The dashboard shows the session cards in one column of at most 380 pixels, next to the timeline. A
user who follows ten or more sub-sessions must scroll that column to compare their states, while the
timeline fills the rest of the window even when the user does not read it.

Once the change ships, a 1440-pixel-wide window shows three or more session cards side by side. One
click on any card shows that session's timeline without leaving the grid.

## Detailed design

### Layout toggle

The session list's header gains two buttons, **List** and **Grid**. The page stores the choice in
`localStorage` under `hub.layout`, as `list` or `grid`. Without a stored choice, the page uses `list`,
so an existing user sees no change. A static export from `session-hub export` offers the same toggle.

### Grid

The grid keeps the three groups of the list ("Needs action", "Working and waiting", "Done"), their
order, and the content of each card. Within a group, the cards fill the window in columns at least
280 pixels wide. A narrower window shows one column without horizontal scrolling.

### Detail panel

In the grid layout, the timeline section becomes a detail panel: the same element with the same tabs
(feed, swimlanes, and collections), the same filters, and the same **Delete session** button. The panel
starts closed, beyond the right edge of the window, and covers at most 720 pixels when open. On a
narrow window the panel covers the full width below the page header.

| Action | Result |
|---|---|
| Click a card, or press Enter or Space on it | Selects the session and opens the panel |
| Click another card while the panel is open | Shows the other session in the open panel |
| Click the selected card again | Closes the panel and clears the selection |
| Press **All sessions** in the session list's header | Opens the panel without a session filter |
| Press the panel's close button, or Escape | Closes the panel and clears the selection; in a non-empty search field, Escape first clears the field |
| The selected session disappears (deleted here or by another viewer) | Closes the panel |

The panel is not modal: the visible part of the grid stays usable while the panel is open. Opening
the panel moves the keyboard focus to it, and closing it returns the focus to the
card, or to **All sessions** when the card is gone. A closed
panel is inert, so neither the Tab key nor a screen reader reaches it. With the reduced-motion setting
(`prefers-reduced-motion`), the panel appears without sliding.

The panel scrolls on its own. The bar that announces new events therefore watches the panel's scroll
position in the grid layout, and the window's position in the list layout.

### Scope

The change touches `session_hub/templates/dashboard.html` alone. Events, the store, and the endpoints
stay unchanged. The new labels live in the `MESSAGES` table in English and Japanese.

## Alternatives considered

- **A grid tab next to the feed and the swimlanes.** The tab would repeat the cards that the list
  already shows on the left, and it would leave the grid less than the full width.
- **The timeline below the grid.** A click on a card would change content outside the visible part of
  the page, and the user would lose the card while scrolling down.
- **A grid that shrinks while the panel is open.** Every opening would move the cards, including the
  card under the pointer. An overlay keeps each card in place.
- **The grid as the default.** The list shows the sessions and the live timeline together, which suits
  a few sessions. A user with many sessions opts in once.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
