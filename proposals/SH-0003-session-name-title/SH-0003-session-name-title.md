**English** · [日本語](SH-0003-session-name-title.ja.md)

# SH-0003 — Show the session name as the title

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0003 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Hooks and skills |
| Implementing PR | [#20](https://github.com/0x0c/claude-code-session-hub/pull/20) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

The dashboard shows each session under the name that Claude Code gives it, unchanged. Today the
dashboard shows the `--title` that the agent composes for `session-hub start`. We read the name from
the transcript and attach it to every update that the session sends.

## Motivation

A person knows a session by its name in the Claude Code session list. The agent's own `--title`
differs from that name, and the reader must match the two by hand.

Once the change ships, a card carries the same text as the session list. After a rename, the card
follows on the session's next update, at the latest when its current turn ends.

## Detailed design

- **Reading the name.** Claude Code writes the name to the transcript. A `custom-title` record holds
  the name that a person or the desktop app set; an `ai-title` record holds a generated name. The
  last `custom-title` wins, and the last `ai-title` is the fallback. `session_hub/session_name.py`
  reads them and returns nothing on a missing or unreadable file.
- **Finding the transcript.** Every hook receives `transcript_path`. We save the path in the
  session's local state, so a command that the agent runs finds the transcript too.
- **Sending.** `deliver` adds the optional field `session_name` to each update that the session
  itself sends. An update by the parent carries no name.
- **Folding.** The hub collapses whitespace in `session_name` and clips it at 200 characters. When a session has a name,
  `apply_event` sets `title` to that name; a later `--title` does not replace it. Every reader of
  `title`, such as the dashboard and `session-hub status`, therefore shows the name.
- **Compatibility.** An older hub stores the extra field and ignores it. Without a name, or for
  events recorded before this change, `title` works as before.

The change adds no text to any model's context.

## Alternatives considered

- **Ask the agent to pass the name as `--title`.** The agent does not know the name, and a rename
  would not reach the hub.
- **Read the desktop app's session files.** The files cover one host, while the transcript covers
  the command line as well.
- **Overwrite `title` in each event.** The store would lose the title that the agent reported.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md, skills)

## References

- [`session_hub/session_name.py`](../../session_hub/session_name.py) — reads the name.
- [`docs/DESIGN.md`](../../docs/DESIGN.md) — the status record.
