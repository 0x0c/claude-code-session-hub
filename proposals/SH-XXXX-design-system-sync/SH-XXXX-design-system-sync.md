**English** · [日本語](SH-XXXX-design-system-sync.ja.md)

# SH-XXXX — Idempotent sync of the design system page

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Developer workflow |
| Implementing PR | [#30](https://github.com/0x0c/claude-code-session-hub/pull/30) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We add `scripts/design_system.py`, which decides what to publish to the design system page. The page is a Claude artifact that documents the dashboard's design tokens and components. The script is idempotent: a sync of a page that is already in step publishes nothing.

## Motivation

An agent built the page with a throwaway script. The page fell behind the dashboard within hours, and nothing in the repository could rebuild it or tell which files were stale. A rebuild could also overwrite a change that a person made on the page.

After this change, a second sync in a row reports "in step: nothing to publish", and a sync never replaces a person's edit without being told to.

## Detailed design

The script reads `session_hub/templates/dashboard.html` for values and rules, and `scripts/design_system_content.py` for the text and the component previews.

| Command | Effect |
|---|---|
| `build --out <dir>` | Writes every generated file |
| `plan --live <dir> --out <dir>` | Compares the build with a fresh copy of the page and writes the files to publish, with `publish.json` |
| `record --live <dir>` | Checks that the page matches the build, then writes the lock |

A script cannot reach the artifact, so an agent reads the page into the live folder, publishes what `publish.json` lists, reads the page again, and runs `record`.

`scripts/design_system.lock.json` holds the hash of each file we last published. The plan compares the build, the page, and the lock:

| Page | Plan |
|---|---|
| Matches the build | Nothing |
| Differs from the build, matches the lock | Update |
| Differs from the build and the lock | Conflict: a person edited it |
| Lacks a file in the lock | Conflict: a person deleted it |
| Lacks a file that is not in the lock | Add |
| Holds a locked file that the build no longer makes | Remove |

A conflict stops the plan with exit code 2. `--overwrite <path>` resolves it in favor of the repository. Files that we never published are left alone. The page's index changes with a publish alone, and keeps every key but `lastChange`.

The build contains no time stamp and stops with an error in three cases: a token has no description or a description has no token, a preview uses a class that the dashboard does not have, or the stylesheet changed shape. The test suite runs the build, so a change to the dashboard that breaks the sync fails the gate.

## Alternatives considered

- **Overwrite the whole page on each sync.** Simple, but it loses edits made on the page and makes a new version each time.
- **Compare with the lock alone.** The script would not need the live copy, but it could not see a person's edit.
- **Store the generated files in the repository.** They would double every change to the stylesheet in review; the lock shows as much with one line per file.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (AGENTS.md)

## References

- [`scripts/design_system.py`](../../scripts/design_system.py) — the script
- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the source of every value
