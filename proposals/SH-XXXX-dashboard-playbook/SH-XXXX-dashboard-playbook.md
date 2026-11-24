**English** · [日本語](SH-XXXX-dashboard-playbook.ja.md)

# SH-XXXX — A playbook of the dashboard's components

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

We add a playbook: one page that shows every component of the dashboard in every state. The hub serves the page at `/playbook`, and the header of the dashboard links to it. `python3 scripts/playbook.py` writes the same page to a file, which opens without a hub.

The page runs the render functions of `session_hub/templates/dashboard.html` itself, so a component in the playbook looks as it does in the dashboard.

## Motivation

A contributor checks a dashboard change today by seeding demo data and looking at the whole page. The demo data reaches few states: no demo session is blocked, abandoned, or done, for example. A change can therefore break a state that nobody looks at.

After this change, one page shows all 14 session states, all 11 event types, and the empty states, in both themes and both languages. Its last section names each dashboard class that no story shows, except the two that place the grid layout's detail panel over the page.

## Detailed design

A *story* is one component in one state. It has a name and a function that returns the nodes to show.

| File | Contents |
|---|---|
| `session_hub/playbook.py` | Builds the page |
| `session_hub/templates/playbook.js` | The stories, their sample data in English and Japanese, and the coverage check |
| `session_hub/templates/playbook.css` | The frame around the stories; every class starts with `pb-` |
| `scripts/playbook.py` | Writes the page to a file |

The build reads the dashboard and changes a copy in three places:

1. It embeds an empty snapshot, the mechanism that `session-hub export` uses, so the page never opens a stream to the hub.
2. It appends `playbook.js` inside the dashboard's script, where the stories can call functions such as `sessionCard` and `eventRow`.
3. It appends `playbook.css` to the head.

The build stops with an error when the dashboard no longer contains one of these places exactly once.

The stories for states and event types iterate over the dashboard's own `STATE_COLORS` and `TYPE_KEYS` tables. A new state or type appears in the playbook without a new story. The page has a theme button, a language button, and frames that a reader can drag to another width.

`GET /playbook` needs the same authorization as the dashboard, including the redirect that drops `?token=` from the Uniform Resource Locator (URL), and contains sample data alone. Story names and the coverage text are English, because the readers are developers; the components themselves follow the page language. The header link is hidden in a file that `session-hub export` writes, because such a file has no hub behind it. Git ignores `playbook.html`, the file that the script writes. The coverage check found one dashboard class that nothing uses, `.sr`, and we remove it.

## Alternatives considered

- **Storybook or a similar tool.** It would bring Node.js packages and a build step to a repository whose dashboard has neither.
- **Copy each component's markup into the page.** The copies would drift from the dashboard.
- **Build the playbook from a script alone.** The hub would not need a new route, but a reader of the dashboard could not reach the playbook by a link.
- **Extend the demo data to every state.** The demo tells one story, and the README screenshots depend on it.

## Progress

- [ ] Design approved
- [x] Implementation with tests
- [x] Documentation updated (AGENTS.md, docs/DESIGN.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the components
- [`scripts/demo.py`](../../scripts/demo.py) — the demo data for the whole page
