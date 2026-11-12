[English](AGENTS.md) · **日本語**

# AGENTS.md — 作業の取り決めと開発メモ

最初に読んでください。人が作業する場合もエージェントが作業する場合も、すべてのセッションはこの文書を前提に始めます。前半は作業の取り決めです。後半の[開発メモ](#開発メモ)には、Session Hubを作る中で分かったことを記録しています。同じことを次のセッションが調べ直さずに済むようにするためです。

## これは何か

Session Hubは、親のClaude Codeセッションが多数のサブセッションの状況を少ないトークンで追えるようにする仕組みです。各サブセッションは、ループバックインターフェース上のハブサーバーへ短い状況のメッセージを送ります（push）。ハブはメッセージを追記専用のイベントとして保存し、Server-Sent Events（SSE）でブラウザーのダッシュボードへリアルタイムに配信します。親はトランスクリプトを読む代わりに、`session-hub attention`が出す数行だけを読みます。

| パス | 中身 |
|---|---|
| `session_hub/` | Pythonパッケージ。スキーマ、イベントストア、ハブサーバー、CLI、hook、コレクション |
| `session_hub/templates/dashboard.html` | ダッシュボードのページ（単体で完結する1ファイル） |
| `bin/session-hub` | インストール方法を問わずパッケージを見つけて実行するラッパー |
| `skills/`、`hooks/`、`prompts/` | 利用者のセッションへ配布するもの（Claude CodeプラグインとAPMパッケージ） |
| `.claude/skills/` | このリポジトリを開発するためのスキル。配布しません |
| `proposals/` | 設計のプロポーザル。変更ごとに1組のファイル（`SH-NNNN-<slug>.md`と`.ja.md`） |
| `docs/DESIGN.md` | 設計の根拠と用語集 |
| `tests/` | テスト（標準ライブラリの`unittest`） |

## 進め方：プロポーザルが先

小さくない変更はすべて、[`proposals/`](proposals/README.ja.md)のプロポーザルから始め、コードはプロポーザルに従って書きます。流れは3つのスキルで進めます。

- [`ideation`](.claude/skills/ideation/SKILL.md)：アイデアをプロポーザルにまとめます。コードは書きません。
- [`implement-proposal`](.claude/skills/implement-proposal/SKILL.md)：`Approved`のプロポーザルを実装します。
- [`propose-and-build`](.claude/skills/propose-and-build/SKILL.md)：設計が固まった小さな変更について、プロポーザルと実装を1つのブランチで作ります。

誤字の修正、テストだけの変更、既存のプロポーザルに書かれている変更には、新しいプロポーザルは要りません。このリポジトリは単独で完結させます。すべてここで開発し、内容の出どころとして他のプロジェクトの名前を書かないでください。

## 書き方

- コードのコメント、docstring、スキル、プロンプト、コミットメッセージ、プルリクエストの文章は**英語**で書きます。
- 利用者が読む文書は**日英の2言語**で用意します。英語の原文`<name>.md`の隣に日本語版`<name>.ja.md`を置きます。対象は`README`、`AGENTS`、`docs/*`、`proposals/README`、各プロポーザルです。両方を同じ変更で更新してください。`scripts/check_docs.py`と`scripts/proposals.py lint`が、対になるファイルがそろっていること、1行目で互いにリンクしていること、見出しの構成が同じであることを確認します。
- 文章を書く前や直す前に、[`document-writing`](.claude/skills/document-writing/SKILL.md)と、言語ごとの[`english-document-writing`](.claude/skills/english-document-writing/SKILL.md)または[`japanese-document-writing`](.claude/skills/japanese-document-writing/SKILL.md)を読み込んでください。これらは下書きの形を決めるもので、書き終えてからの校正用ではありません。
- ダッシュボードは多言語化しています。表示する文言はすべて`session_hub/templates/dashboard.html`の`MESSAGES`表に英語と日本語で入っており、文言を変えるときは両方を更新します。サーバーが送る表示用の文字列（コレクションの名前やグループ名）は、`{"en": ..., "ja": ...}`の形でも書けます。CLIのメッセージとhookがモデルに渡す文は、現在も日本語の製品文言です。プロポーザルで変更を決めるまでは、そのままにしてください。

## 守る原則

1. **トークンを安く保つ。** 親はサブセッションの状況を数行から知り、トランスクリプトは読みません。親を起こす処理や、毎ターンのコンテキストに文を足す処理には理由が必要です。
2. **セッションを止めない。** hookはどんなエラーでも終了コード0で終わり、ターンの終了を止めるのは多くても1回です。
3. **イベントストアだけを正とする。** 画面の表示、コレクション、書き出したファイルは、追記専用のイベントから作る投影です。
4. **ローカルにとどめる。** ハブはループバックインターフェースでだけ待ち受けます。利用者のPCを外部に公開しません。

## 作業の確認

変更を完了とする前と、pushする前に、必ず次のゲートを実行してください。

```bash
scripts/check.sh
```

このスクリプトは、テスト、プロポーザルの形式チェック（`scripts/proposals.py lint`）、2言語の文書のチェック（`scripts/check_docs.py`）を実行します。3つとも成功する必要があります。ダッシュボードを変更したときは、[開発メモ](#実際のブラウザーでダッシュボードを確認する)のとおり、デモデータで画面も確認してください。

## Git

- 作業はブランチで行い、`main`では作業しません（利用者からマージを頼まれた場合を除きます）。コミットメッセージには`feat(dashboard): …`、`fix(hooks): …`、`docs(proposal): …`のように範囲を付けます。
- プルリクエストは、利用者に頼まれたときだけ作ります。

## 開発メモ

各メモには、確かめた事実と、それが重要な理由と、どう対応するかを書いています。

### 決定済みのこと

- **サポートするのはローカル運用です。** サブセッションは利用者のPCで動き、1つのストア（`HUB_STORE`）を共有します。ハブは`127.0.0.1`で待ち受け、サブセッションは`HUB_URL=http://127.0.0.1:8765`へ送ります。利用者のPCをネットワークに公開しないので、トンネルや外部ホスティングは対象外です。
- **ハブからサブセッションへ指示は送りません。** 動いているサブセッションにはhookで指示を届けられますが、ターンを終えたサブセッションを起こす手段はありません。親が`session-hub answer`で回答を記録し、表示された`[HUB/1]`行を自分で届けます。`claude -p`で起動した子には、`claude -p --resume <session_id> "<行>"`でセッションを再開して渡します。
- **「メッセージ」は、サブセッションからハブへ届く更新1件を指します。** サブセッションが親へ送る`[HUB/1]`行は「エスカレーション通知」と呼び、メッセージとは区別します。
- **ナレッジは独立した機能ではなく、コレクションの1つです。** コレクション（match、reduce、view、sinks）はイベントストアの投影で、ナレッジは`finding`イベントを集める組み込みのコレクションです。更新を新しい形でためたいときは、保存先を増やすのではなく、コレクションの定義を足します。

### Claude Codeのhook

- **SessionStart** hookの標準出力は、モデルのコンテキストに入ります。1〜2行にとどめ、ハブが設定されていないときは何も出力しないでください。
- **Stop** hookは、`{"decision": "block", "reason": "..."}`を出力するとターンの終了を止めます。次の呼び出しでは`stop_hook_active: true`が渡されるので、そのときは何も返さないでください。返すとセッションが同じ処理を繰り返します。
- matcherを`TodoWrite|TaskCreate|TaskUpdate`にした**PostToolUse** hookは、`tool_input`からタスク一覧を読めます。そのため、モデルのトークンを使わずに進捗を送れます。`TaskUpdate`にはタスクIDしかないので、`TaskCreate`の時点でIDと名前の対応を記録しています。
- hookに渡される情報には`transcript_path`が含まれます。トークン使用量は、アシスタントの各エントリの`message.usage`を`message.id`で重複を除いて合計して求めます。1つの応答が複数行にまたがることがあるためです。
- hookは`HUB_URL`も`HUB_STORE`も設定されていなければ何もしません。そのため、プラグインを常に有効にしても安全です。

### セッションのID

- クラウドのセッションでは、`CLAUDE_CODE_REMOTE_SESSION_ID`に`cse_<id>`が入っています。セッション関連のツールは`session_<id>`を使うので、接頭辞を書き換えています。ローカルでは`CLAUDE_CODE_SESSION_ID`にUUIDが入っており、これは`claude --resume`が受け付けるIDと同じです。
- Agentツールで起動したサブエージェントは親と同じセッションIDを使うので、別のサブセッションとしては表示されません。サブセッションは別のClaude Codeプロセスとして動かす必要があります。

### APM（Agent Package Manager）での配布

以下は、APM 0.35.1でこのリポジトリを作業用のプロジェクトへインストールして確かめた事実です。

- `.claude-plugin/`があるため、APMはこのリポジトリを**Claudeプラグインのコレクション**として扱います。`apm.yml`に`.apm/`や依存を加えるとAPM形式として扱われてしまいます。そのため、`apm.yml`にはメタデータだけを書き、開発用のスキルはパッケージの外の`.claude/skills/`に置いています。
- APMは各スキルを**名前空間なしで**`.claude/skills/<フォルダー名>/`へ配置します。そのため、配布するスキルには他とぶつかりにくいフォルダー名（`report`ではなく`session-hub-report`）を付け、frontmatterの`name`もフォルダー名と一致させます。
- APMは`hooks/hooks.json`を利用者の`.claude/settings.json`へ統合し、`${CLAUDE_PLUGIN_ROOT}`を`${CLAUDE_PROJECT_DIR}/.claude/hooks/<package>/`に書き換えます。コピーするのは**hookのコマンドが名指しするファイル（`bin/session-hub`）だけ**で、Pythonパッケージはコピーしません。パッケージ本体は`apm_modules/<owner>/<repo>/`に置かれます。そのため`bin/session-hub`はパッケージを探しにいき、見つからないときhookは何も言わずに終了コード0で終わります。
- `apm install <repo> --skill <name>`で、スキルを1つだけインストールできます。`bin/`の実行ファイルは`--trust-bin`を付けたときだけ配置されます。
- YAMLでは、数値に見える値を引用符で囲んでください。`author: 0x0c`は整数の12として読まれます。

### ストアとサーバー

- ストアの各ファイルの書き手は1人だけです（サブセッションは`<id>.jsonl`、親は`<id>@parent.jsonl`）。そのため、ストアをGitで共有してもマージで衝突しません。
- 同じミリ秒に書かれたイベントが、書き手のファイルをまたいで誤った順に並ぶ問題がありました。現在のストアは、ストア全体のロック（`.clock`）の下で、必ず増えていく時刻を払い出します。
- ブラウザーの`EventSource`は`Authorization`ヘッダーを送れません。トークンを設定している場合、ページは`?token=`を一度だけ受け取ってHttpOnlyのcookieに置き換え、リダイレクトでURLからトークンを消します。
- サーバーはメッセージを受け取るたびに、ストアからスナップショットを作り直しています。数千イベントまでは問題ありませんが、それを超えるなら差分で更新する方式に変えてください。

### ダッシュボード

- 更新のたびにDOMを作り直すので、何もしないとCSSのアニメーションが最初からやり直しになります。メッセージ受信時のグローは開始時刻を記録しておき、作り直すたびに負の`animation-delay`を設定して途中から続けています。
- 要素の`hidden`属性は、CSSの`display`の指定に負けます。スタイルシートに`[hidden] { display: none !important; }`を入れています。
- `Object.assign`で`element.style`にカスタムプロパティを設定しても反映されません。`style.setProperty("--name", value)`を使ってください。
- 表示していないタブには古いDOMが残ります。タブを切り替えるときに中身を消さないと、期限切れのグローのような古い状態が残ります。

### 実際のブラウザーでダッシュボードを確認する

- クラウドのサンドボックスにはChromiumとPlaywrightが入っており、どのディレクトリーからでも`require('playwright')`が使えます。
- デモデータを作ってハブを起動します。

  ```bash
  python3 scripts/demo.py --store /tmp/hub-demo
  HUB_STORE=/tmp/hub-demo bin/session-hub serve
  ```

  そのうえで`python3 scripts/demo.py --push http://127.0.0.1:8765`を実行するか、`HUB_URL`を設定して`session-hub`コマンドを実行すると、更新がリアルタイムに届きます。
- ダッシュボードの見た目を変えたら、`node scripts/screenshots.js`でREADMEのスクリーンショット（`docs/images/`、日英両方）を作り直してください。デモデータの言語は`scripts/demo.py --lang en|ja`、ページの言語は`?lang=en|ja`で選べます。
- サーバーのプロセスは`python3 -m session_hub serve`として動きます。止めるときは`pkill -f "session_hub serve"`を使ってください。`session-hub serve`というパターンでは一致しません。

### リポジトリの管理

- `.gitignore`のスラッシュを含まないパターンは、どの階層にも一致します。以前、`dashboard.html`というパターンが`session_hub/templates/dashboard.html`まで無視させてしまい、ダッシュボードがコミットされていませんでした。リポジトリ直下を意味するパターンは先頭にスラッシュを付け（`/dashboard.html`）、ファイルが見当たらないときは`git check-ignore -v <path>`で確認してください。
