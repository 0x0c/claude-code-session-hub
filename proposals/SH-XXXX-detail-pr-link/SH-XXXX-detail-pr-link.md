**English** · [日本語](SH-XXXX-detail-pr-link.ja.md)

# SH-XXXX — Link the pull request in the detail panel

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#34](https://github.com/0x0c/claude-code-session-hub/pull/34) |
| Related | [SH-0010](../SH-0010-session-pr-link/SH-0010-session-pr-link.md) |
<!-- /SH-METADATA -->

## Introduction

When a session holds a pull request (PR), the detail panel of the dashboard links to that PR. The
link appears in the panel's title and on each timeline row that reports the PR or its continuous
integration (CI). We call such a row a PR/CI row.

## Motivation

The detail panel shows the timeline of one selected session. The session's card links to the PR, but
the detail panel shows the number as plain text and only on the timeline rows that report it. A
reader of the timeline must therefore go back to the card, which may be scrolled out of view.

Once the change ships, selecting a session that holds PR 45 shows the link `PR#45` beside the
session's name in the panel's title. A click on the link opens the PR in a new tab.

## Detailed design

- **Title.** The link stands after the session's name in the panel's title, in the list layout and in
  the grid layout. The link is hidden when no session is selected, and when the session's `pr.url` is
  not a web address.
- **Timeline rows.** A PR/CI row turns its PR number into a link when the event carries a web address.
  When the event names a number without a Uniform Resource Locator (URL), the row uses the session's
  `pr.url` if the numbers match. Otherwise the row stays plain text, because the session's current PR
  may differ from the PR of an old event.
- **Safety.** The card, the title, and the rows share one check: the URL must start with `http://` or
  `https://`.
- **Keyboard.** The links on the card and the rows keep the Enter and Space keys from the card. Escape on
  a focused link still closes the detail panel in the grid layout.
- **Compatibility.** The change touches the page alone. Events, the status record, and stored files
  stay as they are.

The change adds no text to any model's context.

## Alternatives considered

- **Link in the title alone.** An old row can name a PR that the session has since replaced, and the
  title cannot reach that PR.
- **Build the URL from the repository name and the number.** The host of the repository is unknown,
  so the link could point to the wrong site.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, skills)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the page.
- [SH-0010](../SH-0010-session-pr-link/SH-0010-session-pr-link.md) — the link on the card.
