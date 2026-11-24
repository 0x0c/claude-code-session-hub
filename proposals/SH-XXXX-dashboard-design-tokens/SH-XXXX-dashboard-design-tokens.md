**English** · [日本語](SH-XXXX-dashboard-design-tokens.ja.md)

# SH-XXXX — Design tokens for the dashboard

<!-- SH-METADATA -->
| Field | Value |
|---|---|
| Proposal | SH-XXXX |
| Author | [@0x0c](https://github.com/0x0c) |
| Status | **Implemented** |
| Topic | Dashboard |
| Implementing PR | [#23](https://github.com/0x0c/claude-code-session-hub/pull/23) |
| Related | — |
<!-- /SH-METADATA -->

## Introduction

We give the dashboard one set of design tokens: named Cascading Style Sheets (CSS) custom properties for color, type, spacing, and corners. Every rule in `session_hub/templates/dashboard.html` takes these values from a token, and a test rejects a literal value.

The same change turns the headings of the session groups ("Needs action", "Working and waiting", "Done") into filled badges, the first component styled from the tokens.

## Motivation

The dashboard names its colors but repeats every size as a literal. The font size 12px appears in 14 rules, and the spacing uses 14 values, some of which differ from a neighbor by one pixel. A new component therefore has no scale to follow. The group headings show the cost: at 11px in the muted color, they are hard to find among the cards below them.

After this change, the headings stand out from the cards, and `scripts/check.sh` fails when a rule sets a font size, spacing, corner, or color to a literal value.

## Detailed design

The `:root` block holds every token:

| Tokens | Use |
|---|---|
| `--bg`, `--panel`, `--ink`, `--muted`, `--line`, `--hover`, `--accent`, `--flash` | Surfaces, text, lines, and accents |
| `--s-*` | The state of a session |
| `--g-action`, `--g-active`, `--g-done`, `--g-archived` | Fill of a group heading, the same in both themes |
| `--on-fill` | Text on a fill |
| `--font-sans`, `--fs-*` | Font family, and five sizes: 11, 12, 13, 14, and 16px |
| `--fw-normal`, `--fw-strong` | Weights 400 and 600 |
| `--space-*` | 1, 2, 4, 6, 8, 10, 12, 14, 16, and 24px |
| `--radius-*` | 3, 4, 6, 8, and 10px, and the pill |

Existing colors keep their values. Values off the scale move to a nearby step: 3px becomes 4px, 5px becomes 6px, and 7px becomes 8px for spacing, and a 2px corner becomes 3px. The timeline marker is the exception, because its margin moves from 5px to 4px to keep it centered on the text line. Sizes that describe a layout rather than a rhythm, such as column widths, icon sizes, and the swimlane drawing, stay literal. The values `0` and `auto`, the 50% corner of a circle, and a layout size that a `calc()` adds to a token stay literal too.

A group heading is a 12px, weight-600 badge with `--on-fill` text on a `--g-*` fill. Its text stays smaller than the 14px session names below it. The fills give white text a contrast of at least 4.5:1 in both themes.

A test reads the stylesheet and checks four rules:

- No rule outside the token blocks sets a font size, weight, spacing, corner, or color to a literal value.
- Every custom property that a rule uses is defined.
- Every status group has a fill.
- The two dark blocks define the same tokens with the same values.

## Alternatives considered

- **Keep every size pixel for pixel.** The scale would need 3, 5, and 7px steps, which no component needs, so the scale would give no guidance.
- **Move the stylesheet to its own file, or add a CSS build.** The dashboard is one self-contained file, which `session-hub export` relies on.
- **Fix the contrast of the state badges too.** White text on several `--s-*` fills falls below 4.5:1, mostly in the dark theme. Fixing it changes the meaning-bearing colors, so it deserves a proposal of its own.

## Progress

- [x] Design approved
- [x] Implementation with tests
- [x] Documentation updated (AGENTS.md)

## References

- [`session_hub/templates/dashboard.html`](../../session_hub/templates/dashboard.html) — the stylesheet
- [`docs/DESIGN.md`](../../docs/DESIGN.md) — what the dashboard shows
