---
name: document-writing
description: Apply this repository's language-independent prose rules when writing or revising proposals, documentation, skills, or code comments. Use it together with english-document-writing, before drafting.
---

<!--
The language-agnostic principles are distilled from Jeffrey Scott Vitter,
"Structure + Style = Communication" (The University of Kansas, 2011).
-->

# Technical-writing norm

Session Hub's writing is argued prose: a proposal under `proposals/` and a document under `docs/`
each make a case a reader must be able to follow. This skill is the authoritative norm for that
prose. Invoke it **before** you write or revise, not after — it shapes the draft, it is not a
proofreading pass.

**Load every file under [`references/`](references/) before drafting, together with this file.**
Apply this norm in full, not step by step: a session that loads references on demand could apply a
subset and still believe it followed the norm.

- [`references/structure.md`](references/structure.md): the layout of a whole document — the title
  and opening, heading order, the units of a procedure step, how terms relate, the main path versus
  the extras, and visual versus semantic breaks.

- **Scope.** Every proposal (`proposals/SH-*.md`), every document under `docs/`, the `README.md`,
  and every skill under `skills/` and `.claude/skills/`. Code comments and docstrings follow the
  sentence-level rules here (clarity, no filler, active voice) but not the document-structure rules.
- **Language.** Write code comments, docstrings, skills, prompts, commit messages, and pull request
  text in **English**, under [`english-document-writing`](../english-document-writing/SKILL.md).
  User-facing documents are **bilingual**: the English original `<name>.md` and a Japanese mirror
  `<name>.ja.md` next to it (`README.ja.md`, `docs/DESIGN.ja.md`, `AGENTS.ja.md`,
  `proposals/SH-0001-<slug>.ja.md`). Write the mirror under
  [`japanese-document-writing`](../japanese-document-writing/SKILL.md), and update both files in the
  same change. Where a language layer overlaps these principles, its specific wording governs.
  The dashboard's labels live in its `MESSAGES` table in both languages. The command-line interface (CLI) messages and the
  hook texts are Japanese product strings; changing their language needs its own proposal.
- **Enforcement is a review-time norm, not a continuous integration (CI) gate.** Judging clarity, emphasis, and argument order
  needs semantic judgment, so people (and the self-review pass in the proposal skills) check it.

## Language-agnostic principles

- **Draft top-down, version by version.** Do not write a long argued section linearly from its
  first sentence. Build it in passes: first a rough outline of the points in the order you will
  treat them; then the section titles and each section's main idea; then subideas and a story line;
  then the near-final prose. The outline forces the organization the reader will need.
- **Go for clarity and simplicity.** On review, cut every word, phrase, and sentence that carries
  no meaning. Streamlining is a required pass, not a nicety.
- **State the contribution up front.** A proposal's Introduction and Motivation state the problem,
  the background, the contribution, and why it matters — before the detail. A reader who stops after
  the first two paragraphs should still come away with the point.
- **Say how a later reader could tell the contribution arrived.** Alongside the contribution, a
  proposal's Motivation names one observable difference the change is meant to produce — a change in
  behavior, in output, or in a quantity a reader could later check against the shipped result. That
  outcome is not the proposal's *Progress* checklist, which tracks whether the work landed rather than
  whether the predicted effect followed. A number is optional; "the dashboard shows a waiting
  sub-session within a second of its question, instead of after the next poll" serves as well as
  one, because a reader can still tell whether it held.
- **The two stress points of a sentence are its beginning and its end.** The end carries the most
  emphasis, so reserve it for the most important element. Move from the known to the unknown, from
  the given to the new, from background to result. Put transitional and background words
  ("Therefore", "However", "In the last section") at the front, saving the content for the end.
- **Keep the verb close to the subject.** A long clause wedged between a subject and its verb makes
  a sentence hard to parse. Rewrite so the verb arrives early, then let the qualifications follow.
- **Prefer the active voice, and write as "we".** The active voice is clearer and shorter; the
  first-person plural keeps it active without the "I" of a personal essay.
- **Cut filler.** Drop words and phrases that add no meaning — "actually", "basically",
  "essentially", "it is important to note that", "note that", a bare "now". Keep "thus" /
  "therefore" only where they genuinely signal a conclusion.

## Paragraph structure

Treat the paragraph, not only the sentence, as the unit of argument. A reader must be able to follow
the case being made paragraph by paragraph, without re-reading to find where one point ends and the
next begins.

- **One topic per paragraph.** A paragraph that mixes several beats of a narrative (investigating,
  reporting, verifying, evaluating) is really several paragraphs. Split it so each paragraph carries
  exactly one step.
- **Front-load the topic.** A reader who reads only a paragraph's first sentence should know what
  the paragraph is about. Do not bury the topic after a run-up.
- **Open on the logical relation to what came before.** Start the paragraph with the connective that
  states how it relates to the previous one ("therefore", "in fact", "however", "even this example
  alone shows"), not partway through.
- **Argue in one direction.** Reach a conclusion, then dispose of objections, then stop — do not
  restate the conclusion afterward. State it once.
- **Do not let an aside interrupt the climax.** Handle an anticipated objection (an example that
  might look contrived, a preemptive caveat) at a paragraph or section boundary, not right after the
  moment it would otherwise interrupt.
- **Name a misreading before correcting it.** When a reader is likely to draw the wrong conclusion,
  state that wrong conclusion explicitly, then give the real one — do not only assert the correct
  account and leave the misreading unaddressed.
- **Justify a denial in the same sentence.** When writing "A, not B", give the reason for ruling out
  B in that sentence rather than leaving it implicit.
- **Do not preview the payoff.** A number or fact meant to land with impact belongs in the paragraph
  where it lands, not foreshadowed in an earlier one.
- **Place forward references at a boundary.** "Covered in a later section" belongs at the end of a
  paragraph or section, once the point in hand is settled — not dropped mid-argument, where it
  breaks the reader's flow.
- **Quote the exact claim you are denying.** When you deny or qualify something, name the specific
  proposition you are ruling out — a vague denial ("not everything is solved") tells the reader
  nothing; naming the precise claim that is false does.

## Self-contained prose

A document must be understandable on its own. A reader who has not read anything else in the
repository — no other proposal, no other page under `docs/`, no earlier commit — must still be able
to follow it start to finish.

- **Never assume prior reading.** Do not write as though the reader already read a linked document,
  an earlier proposal, or an earlier section of the same document. Give each piece the background it
  needs in place.
- **Spell out an abbreviation or acronym on first use.** Write the full term, with the acronym in
  parentheses right after — "Server-Sent Events (SSE)" — then the acronym alone for the rest of the
  piece. A Japanese document writes the term followed by full-width parentheses:
  「Server-Sent Events（SSE）」「プルリクエスト（PR）」. Re-expand the acronym if a long document's later
  section could plausibly be read on its own. `scripts/acronyms.py` checks the first use of every
  acronym it knows; add a new acronym and its expansions to its table when you introduce one.
- **Define a term where you introduce it, and let a cross-reference only send the reader further.**
  A link is a supplement for a reader who wants depth — for elaboration, the canonical wording of a
  cross-cutting rule, or the record — never a substitute for the context this document needs at
  first use, and never the only place a fact the current sentence depends on is stated.
- **No omissions.** Do not skip a step, a definition, or a piece of context because it "should be
  obvious" or "is covered elsewhere". If a reader would have to guess or go looking, the document is
  not yet self-contained.

## Minimize anaphora

An anaphor — a pronoun or demonstrative that points back to something named earlier ("it", "this",
"that", "the former") instead of renaming it — costs the reader a lookup: the reader must hold the
earlier antecedent in memory, then resolve the pointer before the sentence means anything. Reserve an
anaphor for an antecedent that is unmistakable, one sentence back, and within the same paragraph;
beyond that, or once a paragraph, list, or heading boundary intervenes, repeat the noun.

- **Repeat the noun once the antecedent is more than one sentence back, or crosses a paragraph, a
  list, or a heading.** By the time the reader reaches a boundary like that, an antecedent introduced
  before it is no longer active in working memory, so pointing back to it forces a return trip. Name
  the thing again instead.
- **Repeat the noun when more than one candidate antecedent is nearby.** A pronoun that could resolve
  to either of two nouns mentioned in the same stretch of prose forces the reader to guess, then
  double back to confirm the match. Name the one intended.
- **Do not chain an anaphor onto another anaphor.** A "this" pointing to a sentence that itself
  used "it" makes the reader resolve two pointers instead of one. Resolve each reference to the
  concrete noun, not to the previous pronoun.
- **Disambiguate in place instead of sending the reader back.** When an abstract phrase's referent is
  not obvious from the immediate context, name it with a parenthetical aside at the point of use
  rather than leaving the reader to recover it from an earlier passage.

## Mechanical habits

These habits keep sentences readable without a linter. Write to them in the first draft; a short
paragraph fixed right away costs less than a finished document full of long sentences.

- **One clause, one sentence.** Keep a sentence near 100 characters. Split a sentence that needs
  "because", "which", or "so that". Turn a sentence that needs a colon before a list into a bullet
  list instead.
- **Cap commas at three.** A fourth comma is the same signal as a too-long sentence. Split the
  sentence, or turn the enumeration into a list.
- **Prefer a list or a table.** A two-item list beats one long sentence naming both options. Put a
  comparison across options in a table instead; a long caveat per option fits a table cell.

## Verify your work

After drafting, reread once against sentence-level technique: does the piece lead with its
contribution, does each sentence end on its most important element, is the verb near its subject, and
is every sentence free of filler?

Reread again against paragraph structure: does every paragraph carry exactly one topic announced in
its first sentence, and does the argument move in one direction without restating its conclusion?

Reread a third time against self-containment: could a reader who has not read anything else in the
repository follow this piece start to finish, with every acronym expanded and every term defined
where it is first used?

Reread a fourth time against anaphora: does every pronoun or demonstrative resolve to a single,
nearby, unambiguous antecedent, with the noun repeated everywhere it does not?

Reread a fifth time against document structure
([`references/structure.md`](references/structure.md)): could a reader find the order to read and
work in, how the terms relate, the exact operation and input, and the sign of success, without
guessing any of them?

Then run the same rereads under the layer for the language you wrote:
[`english-document-writing`](../english-document-writing/SKILL.md) for English, or
[`japanese-document-writing`](../japanese-document-writing/SKILL.md) for a Japanese mirror. Finally,
run `python3 scripts/check_docs.py` to confirm every bilingual page has its mirror and both
language-switch links.

## References

- Jeffrey Scott Vitter, *Structure + Style = Communication* (The University of Kansas, 2011) — the
  source of the language-agnostic principles above.
- nakamura001, "Codexの作成する技術ドキュメントを読みやすくする" (2026-10-09) — the source of the
  document-structure rules in [`references/structure.md`](references/structure.md).
- [`english-document-writing`](../english-document-writing/SKILL.md) and
  [`japanese-document-writing`](../japanese-document-writing/SKILL.md) — the two language layers
  beneath this norm.
