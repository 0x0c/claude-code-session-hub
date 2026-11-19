[English](README.md) · **日本語**

# プロポーザル

プロポーザルは、Session Hubへの1つの変更について、作る前にその必要性と設計を論じる短い設計文書です。小さくない変更はすべて、このディレクトリーのプロポーザルから始めます。各プロポーザルは、英語の原文と日本語版の2つのファイルで1組です。プロポーザルには、解決する問題、選んだ設計、採らなかった代替案を記録します。後から読む人が、コードがなぜその形なのかを理解できるようにするためです。

## プロポーザルの状態

各プロポーザルは、決まった状態を順に進みます。現在の状態は、メタデータ表の「状態」の行に記録します。

| 状態 | 意味 | この状態にする人 |
|---|---|---|
| Proposed | 作者がプロポーザルを書き、レビューを依頼している状態です。 | 作者（作成時） |
| Approved | メンテナーが設計を承認した状態です。誰が実装しても構いません。 | メンテナー（レビュー時） |
| In progress | 誰かがブランチで実装している状態です。 | 実装者（着手時） |
| Implemented | 変更が取り込まれた状態です。実装したプルリクエスト（PR）へのリンクが`実装PR`の行にあります。 | 実装者（実装のPRの中で） |
| Deferred | 設計は妥当ですが、今は作らないと決めた状態です。 | メンテナー |
| Rejected | 変更しないと決めた状態です。プロポーザルは記録として残します。 | メンテナー |

状態の移り変わりは、[`.claude/skills/`](../.claude/skills/)にある3つのスキルで進めます。

- [`ideation`](../.claude/skills/ideation/SKILL.md)は、大まかなアイデアを`Proposed`のプロポーザルにまとめます。製品のコードには触れません。
- [`implement-proposal`](../.claude/skills/implement-proposal/SKILL.md)は、`Approved`のプロポーザルを実装し、`Implemented`にします。
- [`propose-and-build`](../.claude/skills/propose-and-build/SKILL.md)は、設計が固まった小さな変更について、プロポーザルと実装を1つのプルリクエストにまとめます。

## プロポーザルを追加する

ファイルは手で作らず、スクリプトで作ります。スクリプトは[`TEMPLATE.md`](TEMPLATE.md)と[`TEMPLATE.ja.md`](TEMPLATE.ja.md)からメタデータ表を埋め、番号の代わりに仮の識別子（ID）`SH-XXXX`を付けます。

```bash
python3 scripts/proposals.py new --slug push-retry --title "Retry pushes with backoff" \
  --title-ja "プッシュの再試行" --topic Protocol --author <github-handle>
```

コマンドは、作った2つのファイルのパス（例：`proposals/SH-XXXX-push-retry.md`と`proposals/SH-XXXX-push-retry.ja.md`）を表示します。英語のファイルの`TBD`の節は、[`document-writing`](../.claude/skills/document-writing/SKILL.md)と[`english-document-writing`](../.claude/skills/english-document-writing/SKILL.md)のスキルに従ってすべて埋めます。そのうえで、日本語版を[`japanese-document-writing`](../.claude/skills/japanese-document-writing/SKILL.md)に従って書きます。

### プロポーザルに番号が付く仕組み

プロポーザルは、レビュー中もマージの時点でも仮のID`SH-XXXX`のままです。ブランチ上で番号を選ぶと、同時に開いた2つのブランチが同じ番号を取ってしまいます。そこで、`proposal-id`ワークフロー（`.github/workflows/proposal-id.yml`）が`main`の上で番号を付けます。

1. `SH-XXXX-<slug>.md`を追加するプルリクエストは、そのまま`main`にマージします。
2. ワークフローが`python3 scripts/proposals.py allocate`を実行します。このコマンドは、仮IDの組ごとに、使用中のどの番号よりも大きい次の番号をスラッグ順に割り当て、両方のファイルを`git mv`で改名します。IDを書き換えるのは、IDがそのプロポーザルを指す箇所だけです。対象はファイル名、タイトル、メタデータの行です。仮ID`SH-XXXX`に言及する本文はそのまま残します。
3. `python3 scripts/proposals.py guard`がコミットを検査します。コミットが`proposals/`の中だけを変更していること、すべてのプロポーザルが形式チェックに通ることを確かめます。そのうえでワークフローはコミットを`main`にプッシュし、マージしたプルリクエストに割り当てた番号をコメントします。

したがって、番号はマージ順に並び、却下されたプロポーザルが番号を消費することはありません。ここから2つのルールが生まれます。

- 新しいプロポーザルを別のプロポーザルからリンクするときは、仮IDのファイル名でリンクします。`allocate`がそのリンクを書き換えます。他の文書からは（このREADMEも含めて）、番号が付くまでリンクしません。そのようなリンクは形式チェックが報告します。
- ワークフローは、ブランチ保護を迂回できるGitHub Appとして`main`にコミットします。そのIDと秘密鍵を、シークレット`AUTOMATION_BOT_APP_ID`と`AUTOMATION_BOT_PRIVATE_KEY`に保存します。両方がそろうまでワークフローは何もせず、プロポーザルは仮IDのままです。

## プロポーザルの形式

プロポーザルは、英語の`SH-NNNN-<slug>.md`と日本語の`SH-NNNN-<slug>.ja.md`の2つのMarkdownファイルです。形式チェック（`python3 scripts/proposals.py lint`）は、両方のファイルに次のルールを適用します。

- **言語の切り替え。** 1行目で、もう一方のファイルにリンクします。英語のファイルでは`**English** · [日本語](SH-NNNN-<slug>.ja.md)`、日本語のファイルでは`[English](SH-NNNN-<slug>.md) · **日本語**`です。
- **タイトル。** 最初の見出しは`# SH-NNNN — <Title>`で、区切りはemダッシュです。
- **仮ID。** マージ前は、ファイル名、タイトル、`提案`の行で、`SH-NNNN`の代わりに`SH-XXXX`を使います。
- **メタデータ表。** `<!-- SH-METADATA -->`と`<!-- /SH-METADATA -->`の間の表に、`Proposal`、`Author`、`Status`、`Topic`、`Implementing PR`、`Related`の6行をこの順に書きます。
  - `Author`は、作者のGitHubハンドルのリンクです。ハンドルは推測せず、作者に確認してください。
  - `Status`は、上の6つの状態のどれかを太字で書きます。
  - `Topic`は、Protocol、Hub server、Dashboard、Collections、Hooks and skills、Distribution、Developer workflowのどれかです。
  - `Implementing PR`は、実装のプルリクエストができるまでは`—`で、その後はそのリンクです。
  - `Related`は、`—`か、他のプロポーザルへのリンクです。
- **節。** 次の6つの第2レベルの見出し（H2）の節を、この順に置きます。
  1. *Introduction*：変更とその貢献を1〜2段落で述べます。
  2. *Motivation*：問題とその重要性、そして変更によって観察できる違いを1つ述べます。後から読む人が、変更の効果を確かめられるようにするためです。
  3. *Detailed design*：実装とレビューができる程度に、変更を正確に説明します。
  4. *Alternatives considered*：採らなかった設計を、それぞれの理由とともに挙げます。
  5. *Progress*：チェックリストです。`Implemented`のプロポーザルでは、すべての項目にチェックが入ります。
  6. *References*：プロポーザルが前提とするコード、文書、過去のプロポーザルへのリンクです。
- **日本語版。** 日本語のファイルでは、同じ6行のメタデータに日本語の見出し（提案、作者、状態、トピック、実装PR、関連）を、同じ6つの節に日本語の見出し（はじめに、動機、詳細設計、検討した代替案、進捗、参考資料）を使います。メタデータの値は、すべて英語のファイルと一致させます。
- **空欄を残さない。** コミットする時点で、`TBD`のままの節があってはいけません。

## プロポーザルの一覧

```bash
python3 scripts/proposals.py list
python3 scripts/proposals.py list --status Approved
python3 scripts/proposals.py list --grep dashboard
```

## 未整理のアイデア

まだ形になっていないアイデアは、ここに1行の箇条書きで追加します。範囲が固まったら、番号付きのプロポーザルにします。

- **文書用の文章チェッカー。** 文章のスキルは、現在はレビュー時の規範です。textlintのような機械的なチェックがあれば、長すぎる文や不要な言葉をレビュー前に見つけられます。
