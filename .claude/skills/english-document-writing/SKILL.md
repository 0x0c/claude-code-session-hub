---
name: english-document-writing
description: Apply the English prose mechanics when writing, translating, or revising English proposals, documentation, skills, or code comments. Use it together with document-writing.
---

<!--
The English mechanics are distilled from Jeffrey Scott Vitter,
"Structure + Style = Communication" (The University of Kansas, 2011).
-->

# Technical-writing norm for English prose

This skill is the English layer of the repository's prose norm. It holds the mechanics that only
English grammar and typography need — the choices that have a single right answer in English.

It sits beneath the language-agnostic [`document-writing`](../document-writing/SKILL.md) skill. When
you write or revise English prose, apply **both**: `document-writing` for the shared writing technique
(top-down drafting, sentence stress, subject–verb proximity, active voice, cutting filler), and this
skill for the English mechanics below. Invoke both **before** you write, not after.

When you translate existing Japanese text, rewrite it into natural English under both skills rather
than rendering it sentence by sentence. Keep the meaning, the structure that serves the reader, and
every fact; drop the phrasing that only made sense in Japanese.

## English-specific mechanics

- **Formal word choice.** Use "many" or "much", not "a lot of". Spell out contractions in formal
  text. Reserve symbols and abbreviations for formulas; in prose, spell out the word (write "for
  all", not "∀"; "such that", not "s.t.").
- **Serial (Oxford) comma.** In a list of three or more items, put a comma before the final "and"
  or "or": "the store, the server, and the dashboard".
- **That vs. which.** Use *that* (no comma) for a restrictive clause that specifies which thing you
  mean. Use *which* (set off by commas) for a non-restrictive clause that adds information not
  needed to identify the thing.
- **No bare "this" / "that" as a noun.** Name what it points to: "this behavior", "that
  constraint", not a lone "this".
- **No singular "they" for an unspecified single person.** Reword to the plural ("reviewers raise
  their hands") or a role, rather than "each reviewer raised their hand".
- **Dashes.** A hyphen joins a compound adjective ("push-based delivery"). An en-dash marks a
  range ("steps 3–7") with no surrounding spaces. An em-dash sets off an aside for emphasis — with a
  space on each side, per this repository's convention.
- **Numbers.** Spell out a positive whole number below ten used as an adjective ("three sessions");
  use the numeral when it is a noun or ten or above.
- **Colon.** Introduce a list or an elaboration with a colon only after a complete sentence.
- **Headings.** Use sentence case ("Report a question to the parent"), not title case.

## Constructs to avoid

Common style checkers flag these constructs, and each one weakens technical prose. Write around them
from the start.

- **Passive voice that hides the agent.** Write "the hook sends the heartbeat", not "the heartbeat is
  sent".
- **Weakening words.** "only", "just", "simply", "very", and "really" rarely add meaning. Try
  **"alone"**, **"purely"**, or **"merely"** where a restriction genuinely matters, or drop the word.
- **A sentence-initial "So".** It adds no meaning. Drop the opener.
- **"it is" / "there is".** Restate with a real subject: "three sessions wait", not "there are three
  sessions waiting".
- **Vague intensifiers and hedges.** "quite", "somewhat", "fairly", and "various" weaken a claim
  without making it more precise. State the claim, or state its limit.

## Verify your work

Reread the English draft once against the mechanics above, alongside the language-agnostic reread in
[`document-writing`](../document-writing/SKILL.md#verify-your-work).

## References

- Jeffrey Scott Vitter, *Structure + Style = Communication* (The University of Kansas, 2011) — the
  source of the English mechanics above.
- [`document-writing`](../document-writing/SKILL.md) — the language-agnostic umbrella above this layer.
