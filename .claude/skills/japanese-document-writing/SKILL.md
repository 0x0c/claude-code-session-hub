---
name: japanese-document-writing
description: Apply the Japanese prose rules when writing, translating, or revising a Japanese mirror (*.ja.md) of a document, proposal, or the working agreement. Use it together with document-writing.
---

# Technical-writing norm for Japanese prose

This skill is the Japanese layer of the repository's prose norm. Every user-facing document has an
English original (`<name>.md`) and a Japanese mirror (`<name>.ja.md`); this skill governs the mirror.
It sits beneath the language-agnostic [`document-writing`](../document-writing/SKILL.md) skill. Apply
**both** before you write: `document-writing` for structure, paragraphs, self-containment, and
anaphora, and this skill for the rules that only Japanese needs.

The rules below are written in English so that every session can read them; the examples are in
Japanese.

## A mirror, not a literal translation

- **Carry the same facts and the same structure.** The mirror has the same headings in the same
  order, the same tables, the same code blocks, and the same links (pointing to `.ja.md` pages where
  a mirror exists). A reader of either language must learn the same things.
- **Rewrite the sentences into natural Japanese.** Do not follow the English word order. Turn an
  inanimate subject into a natural Japanese clause, turn a passive into an active form where the
  actor is known, and split a long English sentence into two Japanese sentences.
  - Weak: 「この変更は、親が子のトランスクリプトを読む必要をなくすことを可能にします。」
  - Strong: 「この変更で、親は子のトランスクリプトを読まずに済みます。」
- **Keep identifiers verbatim.** Commands, flags, file names, field names, enum values, event types,
  and the `[HUB/1]` lines stay exactly as in the English original.
- **Update both files in the same change.** A change to an English page that alters a fact updates
  its mirror in the same commit, and the reverse holds too.

## Register and sentence form

- **Use the polite form (です・ます) throughout**, in running prose and in bullet lists alike. Do not
  mix in the plain form (である・だ).
- **End a heading, a table cell, or a checklist item with a noun** (体言止め) when that reads more
  naturally: 「導入手順」「進捗」「要対応の一覧」.
- **One sentence, one point.** Aim for 60–80 characters per sentence. Split a sentence that chains
  several 「〜て、〜て」 or 「〜が、〜」 clauses.
- **Cap 読点 (、) at three per sentence.** A fourth is the same signal as a too-long sentence; split
  the sentence or turn the enumeration into a list.

## Word choice

- **Prefer the direct form.** Write 「〜できます」, not 「〜することができます」; write 「確認します」,
  not 「確認を行います」.
- **Write auxiliary verbs and formal nouns in hiragana.** 「〜していきます」「〜とき」「〜こと」
  「〜ため」「〜ください」, not 「〜して行きます」「〜時」「〜事」「〜為」「〜下さい」.
- **Long-vowel mark on loanwords.** Write 「サーバー」「ユーザー」「ブラウザー」「フォルダー」.
- **Avoid vague hedges and fillers.** Drop 「基本的に」「一応」「〜的な」「〜という形で」 unless they
  carry meaning. Use 「など」 only when the list is genuinely open-ended.
- **Avoid double negatives.** Write 「〜する必要があります」, not 「〜しないわけにはいきません」.
- **Keep one Japanese term per concept**, matching the glossary of
  [`docs/DESIGN.ja.md`](../../../docs/DESIGN.ja.md): サブセッション, 親セッション, ハブサーバー,
  メッセージ, イベント, ストア, コレクション, ナレッジ. On first use, add the English term in
  parentheses when a reader may need to match it to the English page or the code:
  「コレクション（collection）」.

## Typography

- **Punctuation.** Use 「、」 and 「。」. Use full-width parentheses （ ） around Japanese text and
  half-width ( ) inside code or around purely American Standard Code for Information Interchange (ASCII) text.
- **No space between Japanese and half-width alphanumerics** in running text:
  「HUB_URL を設定します」 is wrong; write 「HUB_URLを設定します」. Inline code keeps its backticks:
  「`HUB_URL`を設定します」.
- **Numbers and units.** Use half-width digits: 「6秒」「3件」「127.0.0.1」.
- **Quotes.** Use 「 」 for quoting words or user interface (UI) labels; use 『 』 for a quote inside a quote.

## The language switch

The first line of every bilingual page links the two versions:

- English page: `**English** · [日本語](<name>.ja.md)`
- Japanese page: `[English](<name>.md) · **日本語**`

`scripts/check_docs.py` checks that every bilingual page has its mirror and both switch links.

## Verify your work

Reread the Japanese draft once against the rules above, alongside the rereads in
[`document-writing`](../document-writing/SKILL.md#verify-your-work). Then compare the mirror with
the English original heading by heading: the same sections, the same facts, the same links.
