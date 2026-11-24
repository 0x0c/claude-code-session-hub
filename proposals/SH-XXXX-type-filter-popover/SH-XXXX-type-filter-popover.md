**English** · [日本語](SH-XXXX-type-filter-popover.ja.md)

# SH-XXXX — Filter event types from a popover

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#37](https://github.com/0x0c/claude-code-session-hub/pull/37) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

The detail panel's toolbar gets one **Event types** button in place of the row of event-type toggles.
The button opens a popover that floats over the content and holds one checkbox per event type.

## Motivation

The detail panel always shows one toggle button per event type, from start to unarchive. The row takes
vertical space above the timeline, wraps to several lines in a narrow panel, and changes seldom.

Once the change ships, the timeline starts directly below the toolbar. A reader who hides three types
sees **Event types 9/12** on the button without opening the popover.

## Detailed design

- **Button.** The toolbar holds the button before the heartbeat checkbox. The label reads "Event
  types" (種別), followed by the number of shown types and the total, such as 12/12. When at least one
  type is hidden, the button takes the accent color. The count keeps its width, so ticking a box
  never wraps the toolbar and moves the popover. As the former row did, the button appears in the
  feed and the swimlanes, and it is hidden in a collection tab.
- **Popover.** A click on the button opens the popover; hovering does not. Each event type except the
  heartbeat is a checkbox, and every change applies at once. The heartbeat and oldest-first checkboxes
  stay in the toolbar.
- **Position.** The popover uses the Popover application programming interface (API) and draws in the
  browser's top layer, so neither the panel's overflow nor a sticky header clips it. The script places
  the popover below the button, or above it when that side has more room, and keeps it inside the
  window. A popover taller than the available room scrolls. The script places it again when the page
  scrolls, the window resizes, or the content above the button changes size.
- **Staying open.** The popover stays open while the reader ticks boxes, while live updates redraw the
  page, and while the reader changes the language with the header's button.
- **Closing.** A click outside, Escape, or a second press of the button closes the popover. So does
  closing the grid's panel or showing a collection tab. Escape returns the focus to the button and
  closes the popover alone; a second Escape closes the grid's panel.
- **Accessibility.** The button carries `aria-expanded` and `aria-controls`. The popover is a labelled
  group, and it follows the button in the tab order.
- **Compatibility.** The change touches the page alone, and the selection of types still lasts until
  the page reloads. Events and stored files stay as they are.

The change adds no text to any model's context.

## Alternatives considered

- **An absolutely positioned box in the toolbar.** The grid's panel scrolls and is transformed, so it
  would clip the box or bound its position.
- **`popover="auto"`.** The browser would close the popover on a click of the language button.
- **A modal dialog.** The reader could not see the timeline change while ticking boxes.
- **Opening on hover.** Hovering does not exist on a touch screen, and the popover would open by
  accident.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (docs/DESIGN.md, playbook)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the page.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) — the description of the timeline's filters.
