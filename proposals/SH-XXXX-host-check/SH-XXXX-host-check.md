**English** · [日本語](SH-XXXX-host-check.ja.md)

# SH-XXXX — Refuse hub requests for a foreign host name

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Hub server |
| Implementing PR | [#29](https://github.com/0x0c/claude-code-session-hub/pull/29) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

A hub without a token refuses every request whose `Host` header does not name the loopback interface.
The check keeps a web page from reading or changing the hub through Domain Name System (DNS) rebinding.

## Motivation

In DNS rebinding, a page on `http://evil.example:8765` loads, and its owner then points
`evil.example` at `127.0.0.1`. The browser treats the hub as same-origin with that page. The hub
listens on the loopback interface and, by default, needs no token. The page can therefore read every
message, push false messages, and delete sessions.

Once the change ships, a request with `Host: evil.example:8765` gets `403`, and the dashboard and the
commands work as before.

## Detailed design

- **When:** the hub has no token. A hub with a token may serve any name, and a rebound page has no
  cookie for that token.
- **Where:** right after the hub reads the request headers, before it looks at the method or path.
  The check thus covers every endpoint, including `/healthz` and endpoints added later.
- **Accepted names:** `127.0.0.1`, `localhost`, and `::1`, in any letter case and with any port. The
  port is not compared, so a forwarded port works.
- **Refusal:** `403` with a JavaScript Object Notation (JSON) error that names both remedies, for any
  other name and for a missing or malformed header. The hub then closes the connection, so it never
  parses the unread body as a request.

A reverse proxy or a custom host name in front of a hub without a token stops working. Its user sets
`HUB_TOKEN`. Until then, the client treats `403` on a push like an unreachable hub, so each message
goes to the shared store or the outbox and none is lost. `session-hub doctor` reports such a hub as
not responding.

A cross-origin page that posts straight to `http://127.0.0.1:8765/api/events` sends a loopback `Host`.
That request is not DNS rebinding, and this proposal does not cover it.

## Alternatives considered

- **Refuse a foreign `Origin`.** A browser omits `Origin` on a same-origin `GET`, so a rebound page
  could still read every message.
- **Require a token always.** Every existing setup would need a new setting.
- **Check each endpoint.** A new endpoint could miss the check.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [`session_hub/server.py`](../../session_hub/server.py) — the request handler.
- [`session_hub/client.py`](../../session_hub/client.py) — the loopback names.
