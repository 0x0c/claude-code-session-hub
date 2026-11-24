**English** · [日本語](SH-XXXX-stop-hub.ja.md)

# SH-XXXX — Stop a running hub

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **In progress** |
| Topic | Hub server |
| Implementing PR | — |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We add `session-hub stop`, which stops the local hub server however it was started. The macOS launcher
`Session Hub.command` also stays open until Ctrl-C, even when a hub was already running.

## Motivation

With `HUB_AUTOSTART=1`, a hook starts the hub in the background, where no terminal holds it. Stopping
that hub today takes a process search and `kill`. The launcher does not help: it finds the running
hub, opens the dashboard, and exits at once.

Once the change ships, pressing Ctrl-C in the launcher's window stops the hub in both cases.

## Detailed design

### Hub server

`DELETE /api/server` stops the server. The hub answers `200 {"stopping": true}` first, then leaves its
serving loop, exactly as Ctrl-C does. The hub answers `401` without the right token and `403` to a
client outside the loopback interface. We choose `DELETE` because a page from another origin cannot
send it without a preflight request, which the hub does not answer.

### Command

`session-hub stop [--port N]` targets `127.0.0.1:N`, or else `HUB_URL`, or else
`http://127.0.0.1:8765`. The command refuses a host that is not loopback.

- The hub stops: the command waits until the hub no longer answers, for at most five seconds.
- No hub answers: the command says so and exits 0.
- The hub is too old to know the request: the command prints how to end the process and exits 1.

### Launcher

- **No hub runs:** the launcher runs the server in its window, as before. Ctrl-C or closing the window
  stops the server.
- **A hub already runs:** the launcher opens the dashboard and waits. Ctrl-C runs `session-hub stop`.
  Closing the window leaves the hub running, because that window did not start it. The launcher exits
  when the hub stops for another reason.

### What stays the same

The hub still stores every event, so stopping it loses no message. With `HUB_AUTOSTART=1`, the next
session start launches the hub again.

## Alternatives considered

- **A process id file.** A stale file could name an unrelated process, and a hub started by an older
  version writes none.
- **Replace the running hub from the launcher.** The window would own the server, but every launch
  would interrupt the dashboard and could swap the store.
- **A stop button on the dashboard.** The page cannot start the hub again, so a misplaced click would
  cost more than it saves.

## Progress

- [ ] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/server.py`](../../session_hub/server.py) — the endpoint.
- [`session_hub/cli.py`](../../session_hub/cli.py) — the command.
- [`Session Hub.command`](<../../Session Hub.command>) — the launcher.
