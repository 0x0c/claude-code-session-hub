**English** · [日本語](SH-XXXX-status-guide.ja.md)

# SH-XXXX — Explain every status and state

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Dashboard |
| Implementing PR | [#38](https://github.com/0x0c/claude-code-session-hub/pull/38) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We explain the labels that the dashboard puts on a session. A `?` icon next to each label shows its meaning on hover. A new page, the status guide, lists all the meanings, and the header links to the page.

A *status* is one of the four groups of the session list, such as "Needs action". A *state* is what one session is doing or waiting for, such as waiting for continuous integration (CI). Each state belongs to one status.

## Motivation

The dashboard shows four statuses and 15 states as short labels, and nothing on the page says what they mean. A user cannot tell "Ready for review" from "Not yet reviewable", or learn why a session counts as "Stale?", without reading `docs/DESIGN.md`.

After this change, a user reads the meaning of any status or state badge in the session list without leaving the dashboard.

## Detailed design

The meanings live in the `MESSAGES` table of `session_hub/templates/dashboard.html`, in English and Japanese, under `help.group.<status>` and `help.state.<state>`. The table `STATUS_STATES` lists the states of each status. The icons and the guide read the same entries.

### Help icons

- **Places**: the icon follows the status label in each group heading and the state badge on each card. The timeline, the swimlanes, and a project name carry no icon.
- **Display**: hovering over the icon shows the meaning in the page's tooltip, inside the window. A tap does the same. Neither selects the card nor folds the group. Moving away, scrolling, or pressing Escape hides the meaning.
- **Redraws**: every update replaces the icons, so the listeners sit on the document.
- **Keyboard and screen readers**: the card and the heading are already controls, so the icon takes no focus of its own. Each control carries the meaning as `aria-description`. Keyboard users read the meanings in the guide.
- **Unknown states**: a state without an entry shows no icon.

### Status guide

`GET /guide` returns the page. `session_hub/guide.py` builds it as `session_hub/playbook.py` builds the playbook: a copy of the dashboard in static mode, with `templates/guide.js` and `templates/guide.css` added. For each status, the page shows its meaning and a table of its states: badge, identifier, and meaning.

The page keeps the header's links and its language and theme buttons. The header's title leads back to the dashboard. The route needs the same authorization as the dashboard, including the redirect that drops `?token=` from the Uniform Resource Locator (URL).

The header of the dashboard and of the guide links to the guide as **Status guide**. The link is hidden in a file that `session-hub export` writes, because such a file has no hub behind it.

### Tests

The tests check that every state belongs to one status and that every entry exists in both languages. They also check that `STATUS_STATES` agrees with the states for which the hub sets `needs_action`.

## Alternatives considered

- **The `title` attribute of each badge.** It appears after a delay, never on a touch screen, and nothing shows that it exists.
- **A dialog in the dashboard instead of a page.** A page has an address to share and stays open beside the dashboard.
- **A link to `docs/DESIGN.md`.** The document covers the protocol as well, and a local hub does not serve it.
- **A focusable icon.** It would add one tab stop for every card and heading.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)
- [ ] README screenshots regenerated

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the labels and the icons
- [`docs/DESIGN.md`](../../docs/DESIGN.md) §1.2 — the states and their transitions
