**English** · [日本語](SH-XXXX-knowledge-store.ja.md)

# SH-XXXX — A dedicated knowledge store and a readable knowledge page

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#57](https://github.com/0x0c/claude-code-session-hub/pull/57) |
| Related | SH-XXXX-knowledge-summary-page |
<!-- /SH-METADATA -->

## Introduction

We give the knowledge base its own store: one durable record per knowledge entry, with a stable identifier, the full text, and its revision history. We also rebuild the knowledge page as a searchable list with a detail view, so that a reader can open any entry and read the finding itself.

## Motivation

Knowledge is today a projection of `finding` events. The projection keeps no entry of its own, so an entry has no stable identifier, and its earlier wording survives only as scattered events. The knowledge summary page shows the consequence: each title links to the dashboard's knowledge tab, the dashboard opens with no entry selected, and the reader cannot tell what the link was meant to show. The page also lists every open issue, so a long knowledge base cannot be searched, and the tags are a flat count with no way to filter by them.

Once the change ships, a reader opens one entry from the page and reads its full text, its reporters, and its revisions at a stable address, and narrows a long list by kind, tag, scope, or text without leaving the page.

This proposal reverses a recorded decision. [`AGENTS.md`](../../AGENTS.md) states that knowledge is a collection with no storage of its own, and ground rule 3 makes the event store the single source of truth. The change below keeps the event store the source of truth for everything except knowledge entries, and replaces the first decision.

## Detailed design

### Store

- **Location.** `<HUB_STORE>/knowledge/` holds JavaScript Object Notation (JSON) Lines files. Each file has one writer, as in the event store: `<session-id>.jsonl` for a sub-session and `<session-id>@parent.jsonl` for the parent, so sharing the store through Git never produces a merge conflict.
- **Record.** One line is one revision of one entry: `entry` (identifier), `event_id` (the timeline notice it belongs to), `ts`, `kind`, `title`, `body`, `tags`, `scope`, `status` (`active` or `obsolete`), and the reporting `session_id`. An entry's current state is its latest revision, and the revisions that changed the wording or the status form its history. The reader derives the revision number from the order, so no writer has to count.
- **Identifier.** The identifier is a short hash of the normalized `key`, or of the title when no `key` is given. Two sessions that report the same caveat therefore append to the same entry.
- **Writing.** `session-hub learn` first checks that the store can take a record, then records a short `finding` notice (kind, title, key, status, and `stored: true`) on the timeline, then appends the revision with the notice's event identifier. The check comes first so that a full or read-only disk fails the command before a notice exists whose text was lost. The timeline keeps its "a finding arrived" notice, and the full text lives in the store.
- **Reading.** The server reads the store to build every collection that reads `finding` payloads, and its sinks. A change to any file under `knowledge/` counts as a change of the store, so a watching server rebuilds. The collection definition, `session-hub knowledge`, and `KNOWLEDGE.md` keep their shape.
- **Migration.** When the server starts, it copies every `finding` event that predates the store into the store, keyed by the event identifier so that a second start copies nothing. A notice written by `learn` carries `stored: true`, so the server never copies it. Reading never writes: a reader still shows the old events from memory, so a reader on another machine creates no file that belongs to another writer.

### Compatibility

A machine that still runs an earlier version builds its knowledge collection from the timeline events alone, so it shows every new finding without its text, tags, or scope. We accept this break because the store is shared by machines that run one version, and because keeping the text in the notice as well would put it in two places.

### Page

- **Detail.** `GET /knowledge#<entry>` opens one entry: the full text, kind, tags, scope, reporting sessions (each linking to that session on the dashboard), and the revision list. The title of every entry anywhere on the page links to its detail.
- **List.** The list replaces the fixed sections. It shows one row per entry (kind, title, a two-line excerpt, reporter count, last update) and 50 rows at first, with a control for more.
- **Filters.** Kind chips (with counts), tag chips, a scope filter, a "reported by several sessions" toggle, a full-text search box, and a sort by last update or reporter count. The filter state lives in the address, so a filtered view can be shared.
- **Summary.** The totals stay as one compact row above the list. The kind chips below it carry the counts and apply their kind as a filter.
- **Layout.** Wide windows show the list beside the detail; narrow windows show one at a time. All labels exist in English and Japanese.

### Out of scope

Editing an entry from the page, and similarity-based merging of entries.

## Alternatives considered

- **Keep the projection and only fix the page.** It fixes the dead links and the density, and it leaves entries without identifiers or history. We choose the store because the requester wants entries to be durable records, and the page needs an identifier to link to.
- **Make `KNOWLEDGE.md` the source.** A file in the repository is easy to share, and it has several writers, so it brings back the merge conflicts that single-writer files avoid.
- **Write both the event and the full entry.** The full text then lives in two places that can drift apart. The timeline event carries no body for this reason.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, skills)

## References

- [`AGENTS.md`](../../AGENTS.md), the "Decisions already made" note that this proposal replaces.
- [SH-XXXX-knowledge-summary-page](../SH-XXXX-knowledge-summary-page/SH-XXXX-knowledge-summary-page.md), the page this proposal rebuilds.
