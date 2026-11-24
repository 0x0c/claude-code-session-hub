**English** · [日本語](SH-XXXX-remove-card-delete-button.ja.md)

# SH-XXXX — Remove the delete button from session cards

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Dashboard |
| Implementing PR | — |
| Related | [SH-0002](../SH-0002-delete-session/SH-0002-delete-session.md), [SH-0006](../SH-0006-delete-from-session-list/SH-0006-delete-from-session-list.md) |
<!-- /SH-METADATA -->

## Introduction

We remove the "×" delete button from the session cards, in the list layout and in the grid layout.
Deletion stays available as **Delete session** in the timeline header, and as `session-hub delete` on
the command line. This proposal reverses the button that SH-0006 added.

## Motivation

SH-0006 put a "×" button on every session card. The maintainer finds the button unnecessary in both
layouts. The button puts an irreversible action on every card. Every card also reserves space for the
button, even while the button is hidden, and the reserved space shortens the session names.

Once the change ships, pointing at a card or focusing it shows no "×", and the state badge reaches
the right edge of the card's content.

## Detailed design

In `session_hub/templates/dashboard.html`, we remove:

- the `.carddel` button that `sessionCard` appends, its styles, and the `deletable` class that
  reserves space in the title row;
- the `sessions.deleteOne` label, in both languages;
- the branch that returned the keyboard focus to a delete button after the list is rebuilt. The focus
  still returns to the card of the same session, or to the card that took its place.

We also remove the playbook story and the design system specimen of the button.

`deleteSession(sid)`, the **Delete session** button, the confirmation, the
`DELETE /api/sessions/<session_id>` endpoint, and `session-hub delete` stay unchanged. The button that
closes the grid layout's detail panel also stays, because it closes the panel and deletes nothing.

## Alternatives considered

- **Keep the button in the list layout alone.** Both layouts draw the same card, and the reasons
  against the button hold in both.
- **Move the action into a menu on the card.** The menu would need a control on every card again.
- **Remove deletion from the dashboard.** The timeline header button acts on one selected session, so
  it clutters no card.

## Progress

- [x] Design approved
- [x] Implementation, checked in a browser
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [SH-0006](../SH-0006-delete-from-session-list/SH-0006-delete-from-session-list.md) — the proposal that added the button.
- [SH-0002](../SH-0002-delete-session/SH-0002-delete-session.md) — the endpoint and the header button.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
