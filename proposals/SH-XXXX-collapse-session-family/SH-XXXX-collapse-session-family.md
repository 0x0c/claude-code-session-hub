**English** · [日本語](SH-XXXX-collapse-session-family.ja.md)

# SH-XXXX — Collapse the sub-sessions under a card

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Dashboard |
| Implementing PR | — |
| Related | [SH-0009](../SH-0009-collapse-session-groups/SH-0009-collapse-session-groups.md) |
<!-- /SH-METADATA -->

## Introduction

A user can collapse the sub-sessions under a parent's card in the session list. The number of
sub-sessions on the card becomes a button that hides or shows the cards below. Families start
expanded, and the browser remembers the collapsed ones.

## Motivation

The session list draws sub-sessions as a tree under their parent's card, and the tree is always
fully drawn. A parent with many sub-sessions fills the list, and the user must scroll past its
family to reach the next session. Collapsing the whole group hides unrelated sessions too.

Once the change ships, one click reduces a family to its parent's card, and the family stays
collapsed after a live update and after a page reload.

## Detailed design

The change touches the dashboard page alone, `session_hub/templates/dashboard.html`.

- **Button.** A card with sub-sessions below it, in the same list, shows its number of sub-sessions as
  a button with an arrow marker and `aria-expanded`. The number still counts the direct sub-sessions
  in every group. A card whose sub-sessions are all in other groups keeps the plain number, because
  it has nothing to collapse. The button works on cards at any depth, in both layouts.
- **Effect.** Collapsing a card hides every descendant below it. A sub-session in another group stays
  visible there, so one that needs action is never hidden by its parent's card.
- **State.** Families start expanded. The collapsed ones join the collapsed groups in `localStorage`
  under `hub.collapsed`. The key is the JavaScript Object Notation (JSON) text `{"family": "<session id>"}`,
  which no group key can equal unless a project takes that text as its name. The page works without
  storage; the choice then lasts until a reload.
- **Nested state.** A collapsed card inside a collapsed family stays collapsed when the outer one opens.
- **Order.** A collapsed family still takes the place of its most recently updated member.
- **Hidden activity.** The button glows when a hidden session sends a message, and shows the selection
  color when the selected session is hidden.
- **Card.** A click, Enter, or Space on the button does not select the card.
- **Links.** A link to a session (↳) opens the families that hide its card, as it opens the groups.
- **Focus.** The focus stays on the button across an update. When a focused card becomes hidden in a
  collapsed family, the focus goes to the button that hides it.

## Alternatives considered

- **Start collapsed.** The list would be shorter, and a reader would not see the shape of a family
  until opening it. The user chose the expanded start.
- **Collapse every family with one control.** The user asked to collapse the tree, and one large family
  seldom means that the others are unwanted.
- **A button outside the card.** It would need a column of its own in every list. The number of
  sub-sessions already marks the parents.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — `kidsToggle()`
  and `foldKeys()`.
- [SH-0009](../SH-0009-collapse-session-groups/SH-0009-collapse-session-groups.md) — the collapsible groups.
- [SH-XXXX](../SH-XXXX-session-parent-links/SH-XXXX-session-parent-links.md) — the families.
