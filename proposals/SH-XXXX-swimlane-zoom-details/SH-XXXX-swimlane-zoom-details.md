**English** · [日本語](SH-XXXX-swimlane-zoom-details.ja.md)

# SH-XXXX — Zoom the swimlanes and list their details in a table

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

We let a user zoom and move the time axis of the dashboard's swimlanes, and we list the shown period
in a table below them. The swimlanes draw one horizontal band per session, with state changes as
colored spans and events as dots.

## Motivation

The swimlanes always fit the whole history into the panel. With a few days of history, an hour
shrinks to a few pixels, and neighboring events overlap. The details of an event appear in a tooltip,
one event at a time.

Once the change ships, a user can zoom in to a single minute and read what every session did in the
shown period from one table, without hovering over any dot.

## Detailed design

The change touches the dashboard page and its playbook alone. It adds no event and no server request.

- **Shown period.** The page keeps a span and an end. An unset span shows the whole history, as the
  page did before. An unset end follows the present, so live events stay in view. The choice lasts
  until a reload.
- **Zoom.** Three buttons zoom out, zoom in, and show the whole history. Ctrl or ⌘ with the wheel, and
  a trackpad pinch, zoom around the pointer. A button zooms around the middle, or keeps the present at
  the right edge while the view follows it. The closest zoom shows one minute.
- **Move.** Dragging, horizontal scrolling, Shift with the wheel, and the arrow keys move the period.
  The keys `+`, `-`, and `0` zoom while the swimlanes have the focus. A plain vertical wheel still
  scrolls the page. On a touch screen, the buttons zoom and a drag moves.
- **Axis.** The gridlines fall on round local times. Their step, from one second to several months, is
  the smallest whose labels do not touch. The bar of buttons states the shown period.
- **Drawing.** The page draws the shown period alone at the width of the panel. Session names stay in
  place, and the size of the drawing does not grow with the zoom.
- **Table.** Each row is one event: time, session, event type, state after the event, how long that
  state lasted, and content. The duration appears on the event that began the state, unless the
  session ended in that state. The event that began a state still in effect at the start of the period
  also appears, in a muted color. The toolbar's filters and order apply to the table, and the
  swimlanes keep every band and dot.
- **Links between both.** Hovering over a row or focusing its time draws a vertical line at that time. Clicking the
  time opens the event in the feed. A heartbeat that changed nothing has no link, because the feed
  collapses such heartbeats into one row. During a drag or a wheel gesture, the table updates once the
  movement settles.
- **Labels.** Every label has an English and a Japanese entry in `MESSAGES`.

## Alternatives considered

- **A wide drawing inside a scroll container.** The drawing would reach millions of pixels on a long
  history, and the session names would scroll out of view.
- **A choice of fixed periods, such as the last hour.** The choice cannot show an hour in the middle of
  the history.
- **More detail in the tooltip.** A tooltip shows one moment at a time and cannot be compared or
  searched.
- **Filter the bands and dots too.** Removing events would break the state bands, which follow from all
  of them.

## Progress

- [x] Design approved
- [ ] Implementation with tests, checked in a browser
- [ ] Documentation updated (docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `renderLanes()` and `renderLaneTable()`.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §5.2 — the screen layout.
