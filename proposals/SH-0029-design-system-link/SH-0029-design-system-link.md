**English** · [日本語](SH-0029-design-system-link.ja.md)

# SH-0029 — Link to the design system page

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-0029 |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#47](https://github.com/0x0c/claude-code-session-hub/pull/47) |
| Related | [SH-0014](../SH-0014-dashboard-playbook/SH-0014-dashboard-playbook.md), [SH-0015](../SH-0015-design-system-sync/SH-0015-design-system-sync.md) |
<!-- /SH-METADATA -->

## Introduction

The dashboard header and the Playbook's menu link to the design system page. The hub reads the
address of the page from the environment variable `HUB_DESIGN_SYSTEM_URL`.

## Motivation

The design system page documents the dashboard's design tokens and components. Nothing in the
dashboard leads to the page, although the header links to the Playbook, which covers the same
components. Readers need to keep the address elsewhere.

Once the change ships, a hub with a configured address opens the design system page in one click from
the dashboard, the status guide, and the Playbook.

## Detailed design

- **Configuration.** The hub server reads `HUB_DESIGN_SYSTEM_URL`. The address must start with
  `http://` or `https://` and name a host. The hub ignores any other value.
- **Pages.** The hub writes the address into each page that it serves. The address is escaped so that
  it cannot end the page's script.
- **Header.** **Design system** follows **Playbook**, on the dashboard and on the status guide. The
  link opens a new tab.
- **Playbook.** The Playbook's menu shows the same link below "← Session Hub".
- **No address.** Without an address, the link stays hidden in the header and absent from the
  Playbook's menu.
- **Export.** A file that `session-hub export` writes never carries the address, because the file may
  be shared.

## Alternatives considered

- **Write the address into the repository.** The published page is a private Claude artifact, so the
  link would fail for everyone except its owner. We keep the address out of the repository.
- **Serve the page from the hub.** The design system page lives in the artifact. A local copy would
  create a second page to keep in step.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (README.md, docs/DESIGN.md)

## References

- [SH-0014](../SH-0014-dashboard-playbook/SH-0014-dashboard-playbook.md) — the Playbook.
- [SH-0015](../SH-0015-design-system-sync/SH-0015-design-system-sync.md) — how we sync the design system page.
