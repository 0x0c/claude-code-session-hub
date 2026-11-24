[English](SH-XXXX-proposal-folders.md) · **日本語**

# SH-XXXX — プロポーザルごとにフォルダを分ける

<!-- SH-METADATA -->
| 項目 | 値 |
|---|---|
| 提案 | SH-XXXX |
| 作者 | [@0x0c](https://github.com/0x0c) |
| 状態 | **Implemented** |
| トピック | Developer workflow |
| 実装PR | [#22](https://github.com/0x0c/claude-code-session-hub/pull/22) |
| 関連 | [SH-0001](../SH-0001-merge-time-numbering/SH-0001-merge-time-numbering.md) |
<!-- /SH-METADATA -->

## はじめに

プロポーザルごとに専用のフォルダ`proposals/SH-NNNN-<slug>/`を設けます。フォルダには、英語の原文、日本語版、補助ファイルを収めます。スクリプトは、ばらのファイルの組の代わりに、フォルダの作成と検査と採番を担います。

## 動機

現在は、プロポーザルが増えるたびに、READMEやテンプレートと並んで2つのファイルが`proposals/`の直下に加わります。一覧はプロポーザルの2倍の速さで長くなり、特定のプロポーザルに属する図には置き場所がありません。

変更後の`proposals/`には、プロポーザルごとに1つの項目だけが並びます。フォルダに置いた補助ファイルは、プロポーザルに番号が付くときにフォルダごと移ります。

## 詳細設計

### 配置

```text
proposals/
  README.md, README.ja.md, TEMPLATE.md, TEMPLATE.ja.md
  SH-0001-merge-time-numbering/
    SH-0001-merge-time-numbering.md
    SH-0001-merge-time-numbering.ja.md
```

フォルダと両方のファイルは、同じ名前`SH-NNNN-<slug>`にします。言語を切り替える行は変わりません。別のプロポーザルへのリンクは`../SH-NNNN-<slug>/SH-NNNN-<slug>.md`になり、リポジトリのルートへのリンクには`../`が1つ増えます。

### スクリプト

- `new`は、フォルダとその中の2つのファイルを作ります。同じスラッグの仮のフォルダがあれば拒否します。
- `lint`は、`proposals/`の直下にあるプロポーザル、形式に合わないフォルダ名、英語の原文がないフォルダ、フォルダと名前が異なる`SH-*.md`を報告します。
- `allocate`は、フォルダを`git mv`で改名し、続いて中の2つのファイルを改名します。仮の名前へのリンクは、すべてのプロポーザルのフォルダにあるMarkdownファイルで書き換えます。

### 移行

既存の3つのプロポーザルをフォルダへ移し、リンクもすべて更新します。ばらのファイルを追加するブランチでは、ファイルをフォルダへ移す必要があります。移すまでは`lint`が失敗します。移さずにマージすると、`guard`がすべてのプロポーザルの採番を止めます。

## 検討した代替案

- **状態ごとのフォルダ。** 状態が変わるたびにプロポーザルが移動し、リンクが切れます。状態は、すでに「状態」の行に記録しています。
- **`en.md`や`ja.md`のような短いファイル名。** 名前の繰り返しはなくなりますが、エディターのタブや検索結果から、どのプロポーザルのファイルかがわからなくなります。

## 進捗

- [x] 設計の承認
- [x] テストを含む実装
- [x] ドキュメントの更新（proposals/README.md、AGENTS.md、スキル）

## 参考資料

- [`scripts/proposals.py`](../../scripts/proposals.py) — `new`、`lint`、`allocate`。
- [`proposals/README.md`](../README.ja.md) — プロポーザルの形式。
- [SH-0001](../SH-0001-merge-time-numbering/SH-0001-merge-time-numbering.ja.md) — マージ時の採番。
