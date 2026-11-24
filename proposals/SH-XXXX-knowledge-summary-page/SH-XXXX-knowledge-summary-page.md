**English** · [日本語](SH-XXXX-knowledge-summary-page.ja.md)

# SH-XXXX — Knowledge summary page

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#50](https://github.com/0x0c/claude-code-session-hub/pull/50) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

The hub serves a page at `/knowledge` that summarizes the knowledge collection: how many findings there are, how they split by kind, which ones several sessions reported, and what changed last.

## Motivation

The dashboard's knowledge tab lists every finding as a card. It answers "what do we know?" item by item, but a reader who wants the shape of the knowledge base has to scroll through all of it. The cards also share the screen with the session list and the timeline, so the tab suits working beside the sessions, not reading.

Once the change ships, one page shows the counts, the findings that several sessions reported, the open issues, and the latest additions, and every finding links back to the dashboard.

## Detailed design

- **Route.** `GET /knowledge` serves the page. It follows the token rules of `/guide`: a `?token=` is accepted once and replaced by the cookie.
- **Data.** The page reads `api/snapshot` and uses the built-in `knowledge` collection. It reads the snapshot again every 15 seconds and redraws in place when the language changes. It adds no endpoint and no storage.
- **Page.** The page is the dashboard's script and style with `templates/knowledge.js` and `templates/knowledge.css` added, as the status guide is. Its sections, in order:
  1. **Totals.** The number of active findings, the number of reporting sessions, and one count per kind, colored as the dashboard colors them.
  2. **Open issues.** The active findings of kind `issue`, newest first.
  3. **Reported by several sessions.** Active findings that two or more sessions reported, most reporters first (at most 10).
  4. **Latest.** The 10 most recently reported active findings.
  5. **Tags.** Each tag with its count, most used first (at most 20).
- **Links.** A finding's title links to the dashboard's knowledge tab (`./#col:knowledge`) so that a reader can open the full card there. The header gains a **Knowledge summary** link next to **Status guide**; an exported file hides it, as it hides the other two.
- **Empty and obsolete.** With no active findings the page says so and names `session-hub learn`. Obsolete findings are left out of every count.
- **Language.** Labels exist in English and Japanese in the dashboard's `MESSAGES` table. Finding text appears as reported.
- **Out of scope.** Other collections, filters, and editing.

## Alternatives considered

- **Extend the knowledge tab.** The tab shares its screen with the session list and the timeline, so a summary there stays cramped. A page of its own can be opened, shared, and read on its own.
- **Write a `KNOWLEDGE.md` sink.** A sink serves files in a repository, not a live view. It also needs a path in `collections.json`. The page needs no configuration.
- **A server-side summary endpoint.** The snapshot already holds every item, so the browser can count them. A second projection would give the same numbers twice.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, skills)

## References

- [SH-0023](../SH-0023-status-guide/SH-0023-status-guide.md) — the status guide, whose page structure this page follows.
