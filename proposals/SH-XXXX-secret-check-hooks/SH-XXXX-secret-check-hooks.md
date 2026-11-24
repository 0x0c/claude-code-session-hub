**English** · [日本語](SH-XXXX-secret-check-hooks.ja.md)

# SH-XXXX — Check for secrets before each commit

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Developer workflow |
| Implementing PR | — |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We check each commit for secrets before Git records it. Tracked Git hooks run gitleaks, a secret
scanner, on the staged change and on the commit message. A finding blocks the commit. A
continuous integration (CI) job repeats the scan over the history, because a local hook can be bypassed.

## Motivation

This repository is public, and agents write most of its commits. A key pasted into a fixture or a
commit message becomes public on push, and deleting the key in a later commit does not withdraw it.
Nothing checks for secrets before a commit.

Once the change ships, a commit that stages a Claude OAuth token fails with a message that names the
file and the line, and the output does not show the token.

## Detailed design

### Hooks

The hooks live in `.githooks/`. A contributor enables them once per clone with
`make setup`, described under [Setup](#setup). The path is relative, so the setting covers every linked
worktree whose branch holds the hooks.

| Hook | What it scans |
|---|---|
| `pre-commit` | The staged change |
| `pre-merge-commit` | The result of a merge without conflicts, for which Git skips `pre-commit` |
| `commit-msg` | The commit message |

- **Finding:** the hook exits nonzero, and gitleaks redacts the secret in its output.
- **gitleaks missing:** the hook blocks the commit and names `make setup`.
- **Emergency:** `git commit --no-verify` skips the hooks. The CI job still reports the secret.

### Setup

One command, `make setup`, makes a clone ready for work. It runs `scripts/setup.sh`, which is safe to
run again:

1. It checks that `python3`, `curl`, and `tar` exist.
2. It stops if `core.hooksPath` already names another folder, because replacing the setting would turn
   those hooks off.
3. It downloads a pinned gitleaks into the Git folder, which all worktrees of the clone share. The
   checksum in the script must match before the file is used. macOS and Linux are supported, on x64
   and arm64.
4. It sets `core.hooksPath` to `.githooks`.

A clone that is not set up cannot be worked on unnoticed:

| Where | What happens |
|---|---|
| Claude Code session start | `.claude/settings.json` runs the setup; a failure appears in the context |
| Claude Code edit tools | A PreToolUse hook blocks the edit until the setup is complete |
| `scripts/check.sh` | The gate fails; `make check` runs the setup first |

The edit block applies to this repository alone. Shell commands stay allowed, so that a session can
run `make setup`; a change made through the shell meets the gate and the CI job instead. Without
network access, the first setup fails and edits stay blocked.

### Rules
### Rules

`.gitleaks.toml` extends the built-in rules of gitleaks with two rules:

- `anthropic-api-key` also covers OAuth tokens (`sk-ant-oat01-`), which the built-in rule misses.
- `hub-token` matches `HUB_TOKEN` followed by a literal value of 16 or more characters. A shell
  variable or a short placeholder does not match.

Each allowlist names one rule and one file, so a false positive never disables a rule elsewhere. The
first allowlist covers the content hashes in `scripts/design_system.lock.json`.

### History scan

`scripts/check_secrets.sh` scans every commit reachable from `HEAD`, including what a merge commit
itself changes. The gate (`scripts/check.sh`) runs the script. The `secret-scan` workflow runs
`make setup` and the same script on each pull request and on `main`.

The job reports a secret after the push, so a secret that bypassed the hooks must be revoked.

## Alternatives considered

- **Write our own scanner in Python.** It needs no installation, but we would maintain patterns for
  every provider.
- **Let a commit pass with a warning when gitleaks is missing.** A warning is easy to miss, and the
  setup installs gitleaks wherever we work.
- **Install gitleaks with Homebrew.** The cloud sandbox has no Homebrew, and versions would differ.
- **Ask for the setup in the documentation alone.** Nothing would notice a skipped setup.
- **Use the pre-commit framework.** It adds a Python dependency to a repository that has none.
- **Scan the working folder instead of the history.** The scan would miss a secret that a later commit
  removed, and it would read ignored files and other worktrees.
- **Use a Claude Code hook.** It would not see commits that a person makes.

## Progress

- [ ] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, AGENTS.md)

## References

- [`.githooks/pre-commit`](../../.githooks/pre-commit) — the staged-change check.
- [`.gitleaks.toml`](../../.gitleaks.toml) — the rules and allowlists.
- [`scripts/check_secrets.sh`](../../scripts/check_secrets.sh) — the history scan.
- [gitleaks](https://github.com/gitleaks/gitleaks) — the scanner.
