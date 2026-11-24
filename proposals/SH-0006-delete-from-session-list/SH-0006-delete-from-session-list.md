**English** · [日本語](SH-0006-delete-from-session-list.ja.md)

# SH-0006 — Delete a session from the session list

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0006 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#13](https://github.com/0x0c/claude-code-session-hub/pull/13) |
| Related | [SH-0002](../SH-0002-delete-session/SH-0002-delete-session.md) |
<!-- /SH-METADATA -->

## Introduction

We add a delete button to every session in the dashboard's session list. A user removes a session
with one click and one confirmation, without selecting the session first. The button calls the
existing `DELETE /api/sessions/<session_id>` endpoint, so the store, the hub server, and the
command-line interface (CLI) stay unchanged.

## Motivation

The dashboard offers deletion in one place: the timeline header, after the user selects a session.
Cleaning up the list therefore takes a round trip per session. The user selects the session in the
list, moves to the timeline header, deletes the session, and returns to the list. On a narrow screen
the timeline header sits below the whole list, so a user who looks at the list alone never sees a
way to delete.

Once the change ships, a user removes a session from the list with the list alone on screen, and the
current selection and timeline filter stay in place when the user deletes another session.

## Detailed design

### Markup

The session card is itself a button, so a button inside the card would be a nested control that
keyboard and screen-reader users cannot operate reliably. We wrap each card in a
`<div class="cardwrap">` and place the delete button in the wrapper as a sibling after the card. The
button is a native `<button>` that shows "×". Its accessible name and tooltip name the session
(`sessions.deleteOne`), because a list holds many identical icons.

The button sits at the right end of the title row, in space the row reserves, so the button never
covers the state badge. On a device that can hover, the button appears when the pointer is over the
card or when the card or the button has keyboard focus. On a touch device, the button is always
visible.

### Behavior

The timeline header button and the list buttons share one function, `deleteSession(sid)`:

1. Show the existing confirmation dialog with the session's name and its message count.
2. On confirmation, send `DELETE api/sessions/<session_id>`. While the request runs, every delete
   button of that session is disabled, including after a re-render.
3. On success, clear the selection if the deleted session is the selected one. Otherwise, keep the
   selection. In the grid layout, clearing the selection also closes the detail panel. The `update`
   message that follows removes the card.
4. On a failure, show the server's error in an alert and keep everything.

Every update rebuilds the list, which would drop the keyboard focus. After a rebuild, the page puts
the focus back on the same control of the same session. When that session is gone, the focus moves
to the session that took its place.

A static export shows no list button, for the same reason it shows no header button: a deletion needs
the live hub.

### What stays the same

The timeline header button, the endpoint, the confirmation text, and `session-hub delete` keep their
behavior. Deleting several sessions in one action is out of scope.

## Alternatives considered

- **Nest the button inside the card.** SH-0002 rejected this layout because a nested button is not
  accessible. A sibling button avoids that problem.
- **Keep the header button alone.** The header button requires a selection, which replaces the
  timeline filter the user was working with.
- **Show every list button all the time.** A long list would carry a destructive icon on every row.
  Showing the button on hover and focus keeps the list calm on a desktop.
- **Delete without a confirmation.** The list button is easy to hit by accident and the deletion
  cannot be undone.

## Progress

- [x] Design approved
- [x] Implementation, checked in a browser
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [SH-0002](../SH-0002-delete-session/SH-0002-delete-session.md) — the endpoint, the store deletion, and the header button.
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the dashboard.
