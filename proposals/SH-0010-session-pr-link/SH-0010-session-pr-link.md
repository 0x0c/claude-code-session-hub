**English** · [日本語](SH-0010-session-pr-link.ja.md)

# SH-0010 — Link a session's pull request

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0010 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Hooks and skills |
| Implementing PR | [#26](https://github.com/0x0c/claude-code-session-hub/pull/26) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

When a session holds a pull request (PR), its dashboard card links to that PR. The hooks read the
link from the transcript, so neither the agent nor the user reports it.

## Motivation

A person who watches the dashboard often wants to open the PR that a session works on. The card shows
a PR number when the session reports one with `session-hub pr`, and the number is plain text. A
session that never runs the command shows nothing.

Once the change ships, the card of a session that opened a PR shows `PR#45` after the session's next
update, at the latest when its current turn ends. A click on the number opens the PR in a new tab.

## Detailed design

- **Reading the link.** Claude Code writes a `pr-link` record with `prNumber` and `prUrl` to the
  transcript. `session_hub/pr_link.py` takes the last record and returns nothing on a missing or
  unreadable file.
- **Sending.** `deliver` adds the optional field `pr_link: {number, url}` to each update that the
  session itself sends. An update by the parent carries no link.
- **Validating.** The hub keeps a link whose number is a positive integer and whose Uniform Resource
  Locator (URL) starts with `http://` or `https://` and has at most 500 characters. The hub drops any
  other link and records the rest of the update.
- **Folding.** The status record keeps the link as `pr_link`, and `pr` holds the current PR. A link
  acts when it differs from the previous link, because every update repeats it. The newer of a
  changed link and a `session-hub pr` report wins. A different PR number or URL clears the old PR's
  continuous integration (CI) result and other facts. When a report names the linked number without
  a URL, the link supplies the URL.
- **Showing.** The card turns the PR label into a link when `pr.url` is a web address. A click on the
  link does not select the card. A PR reported without a URL stays plain text.
- **Compatibility.** An older hub stores the extra field and ignores it. Events recorded before this
  change fold as before, except that a report of a different PR clears the old PR's facts.

The change adds no text to any model's context.

## Alternatives considered

- **Ask the agent to pass `--url`.** The agent spends tokens on a fact that the transcript holds, and
  a forgotten report leaves no link. The option still works.
- **Send a separate `pr` event when the link appears.** The sender would need its own state to avoid
  repeats, and a lost event would lose the link.
- **Show every PR that the session opened.** The review gate judges one PR per session. A list
  needs a wider change to the status record.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, AGENTS.md)

## References

- [`session_hub/pr_link.py`](../../session_hub/pr_link.py) — reads the link.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) — the status record.
