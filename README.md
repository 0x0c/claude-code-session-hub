# claude-code-session-hub

親セッションが走らせている複数のサブセッションの状況を、**少ないトークンで・リアルタイムに**一覧するためのツールです。

- サブセッションは状態が変わるたびに `session-hub` コマンドでハブへ **push** し、ハブはそれを**即座に**ブラウザのダッシュボードへ配信します（SSE。ポーリングなし）。
- ダッシュボードでは、要対応（人間待ち・失敗・レビュー可・停滞）を先頭に一覧し、作業中のセッションにはスピナーを表示します。届いた報告は**タイムライン**（フィード / スイムレーン）で時系列にたどれます。
- 親セッションはトランスクリプトを読まず、`session-hub attention` の数行だけで判断します。
- サブセッションが作業で判明した知見・注意点・決定事項は `session-hub learn` で **1 か所（ナレッジ）に集まり**、同じ発見は 1 件にまとまります。どこにどうためて、どう見せるかは**コレクション**として宣言的に定義でき（`collections.json`）、ダッシュボードにタブとして表示され、Markdown などへの書き出しもできます。
- Claude Code プラグインとして、報告手順のスキルと、報告漏れを防ぐ hook（heartbeat・トークン使用量・進捗の自動送信、作業中のまま終了しようとしたときの確認）を同梱しています。

設計の背景・プロトコル・用語は [docs/DESIGN.md](docs/DESIGN.md) を参照してください。

## 必要なもの

Python 3.10 以上（標準ライブラリのみ）。インストールせずに `bin/session-hub` で動きます。`pip install .` で `session-hub` コマンドとして入れることもできます。

## クイックスタート（デモ）

```bash
python3 scripts/demo.py --store /tmp/hub-demo
```

```bash
HUB_STORE=/tmp/hub-demo bin/session-hub serve
```

ブラウザで http://127.0.0.1:8765/ を開きます。別のターミナルで子セッションのふりをして push すると、即座に反映されます。

```bash
python3 scripts/demo.py --push http://127.0.0.1:8765
```

## 使い方（ローカル運用）

サブセッションを手元の PC で動かし、全セッションで同じストア（`HUB_STORE`）を共有する構成です。
ハブサーバーは `127.0.0.1` でのみ待ち受けるので、PC を外部に公開しません。

```
サブセッション A ─┐ POST（127.0.0.1）
サブセッション B ─┼──────────► ハブサーバー ──SSE──► ブラウザ（http://127.0.0.1:8765/）
サブセッション C ─┘                 │
        └ サーバー停止中は共有ストアへ直接書く ─► ~/.session-hub/events/*.jsonl ◄─ 起動時に読み込み
```

### 1. スキルと hook を入れる

**APM（Agent Package Manager）で入れる場合**（プロジェクト単位）:

```bash
apm install 0x0c/claude-code-session-hub --target claude
```

- `.claude/skills/session-hub-report/` と `.claude/skills/session-hub-orchestrate/` にスキルが、`.claude/settings.json` に hook が入ります。
  本体は `apm_modules/0x0c/claude-code-session-hub/` に置かれ、hook は自動でそこを見つけます。
- 依存は `apm.yml` に記録されるので、他の人は `apm install` だけで同じ状態にできます（`apm_modules/` は git 管理外）。
- スキルを 1 つだけ入れるなら `--skill session-hub-report`（子セッション用）または `--skill session-hub-orchestrate`（親用）を付けます。
- `session-hub` コマンドは、最初のセッション開始時に hook が `~/.local/bin/session-hub` を作ります。どこからでも使いたい場合は
  `pip install git+https://github.com/0x0c/claude-code-session-hub` でも入れられます。

**Claude Code プラグインとして入れる場合**（全プロジェクト共通）:

```text
/plugin marketplace add 0x0c/claude-code-session-hub
/plugin install session-hub@session-hub
```

プラグインとして入れた場合、スキル名には `session-hub:` が前に付きます（例 `session-hub:session-hub-report`）。

### 2. 全セッション共通の設定を書く

`~/.claude/settings.json`（ユーザー設定。全プロジェクトのセッションに効く）に次を追加します。

```json
{
  "env": {
    "HUB_URL": "http://127.0.0.1:8765",
    "HUB_STORE": "~/.session-hub",
    "HUB_AUTOSTART": "1"
  }
}
```

- `HUB_AUTOSTART=1` にすると、最初に始まったセッションがハブサーバーを裏で起動します（ログは `~/.session-hub/.server.log`）。自分で起動する場合は外して `session-hub serve` を実行します。
- サーバーが止まっている間のメッセージは共有ストアに直接書かれ、サーバーが起動すると画面に出ます。失われることはありません。
- 特定のプロジェクトだけで使うなら、そのプロジェクトの `.claude/settings.local.json` に書きます。

### 3. 確認する

```bash
session-hub doctor
```

URL・サーバーの応答・ストアの書き込み可否・コマンドの場所・未送信の有無を確認できます。ブラウザで http://127.0.0.1:8765/ を開けばダッシュボードです。

### 4. サブセッションを動かす

ローカルでは各サブセッションが別々の Claude Code セッション（別のセッション ID）である必要があります。

- **人間が並行して起動する**: 別のターミナルや worktree、デスクトップアプリの並行セッションで `claude` を起動する。指示の冒頭に [prompts/child-append-system-prompt.md](prompts/child-append-system-prompt.md) の内容を含めるか、次のように渡す。
- **親がバックグラウンドで起動する**:

```bash
claude -p "<作業内容>" --append-system-prompt "$(sed -e 's/{{PARENT_SESSION_ID}}/<親のID>/' -e 's/{{TITLE}}/<作業名>/' prompts/child-append-system-prompt.md)"
```

Agent ツールのサブエージェントは親と同じセッション ID になるため、別のサブセッションとしては表示されません（区別したい場合はサブエージェントの指示で `session-hub --session <固有のID> ...` を使わせます）。

### 入るもの（APM・プラグイン共通）

`HUB_URL` も `HUB_STORE` もないセッションでは、hook は何もしません。

| 種類 | 内容 |
|---|---|
| スキル `session-hub-report` | いつ・何を報告するか（子用） |
| スキル `session-hub-orchestrate` | 子の起動・`[HUB/1]` への対応・回答の仕方（親用） |
| SessionStart hook | `~/.local/bin/session-hub` を用意し、`HUB_AUTOSTART=1` ならサーバーを起動し、未登録なら `start` を促す 2 行を注入 |
| PostToolUse hook | TodoWrite / TaskCreate / TaskUpdate → タスク進捗と作業中タスク名を自動送信 |
| Stop hook | ターン終了ごとに heartbeat とトークン使用量を自動送信。作業中のまま終えようとしたら 1 回だけ報告を促す（`HUB_STOP_GUARD=0` で無効） |

### （参考）クラウドのサブセッションで使う場合

クラウドのセッションから届く常設サーバーにハブを置き、`HUB_TOKEN` を設定して `session-hub serve --host 0.0.0.0` で起動します。
子の環境で `HUB_URL` を設定し、ハブのホストをネットワーク許可リストに加え、トークンは `Authorization: Bearer` のネットワークシークレットとして登録します。
ブラウザでは最初に `?token=<HUB_TOKEN>` を付けて開きます。手元の PC を外部に公開する構成は想定していません。

## コマンド早見表

子セッション（`HUB_URL` へ push。届かなければ `HUB_STORE` に直接書く）:

```bash
session-hub start --title "作業名" --task-ref "#128" --task "設計=todo:S" --task "実装=todo:M"
session-hub report --phase test --summary "テスト追加中" --task "実装=done"
session-hub ask --kind decision --q "上限は?" --opt 60 --opt 120 --default 120 [--non-blocking]
session-hub pr --number 45 --ci pending --state waiting_ci
session-hub ready --self-review --tests --description
session-hub done --summary "PR #45"
session-hub fail --error "原因"
session-hub flush
session-hub doctor
```

`flush` は、届かずに outbox へ溜まったイベントを再送します。`doctor` は設定を確認します。

知見・注意点の記録と参照:

```bash
session-hub learn --kind caveat --title "CI の Redis は 6.2" --body "根拠と対処" --tag ci --scope tests/
session-hub knowledge --scope tests/ [--kind caveat] [--body]
session-hub collection knowledge [--format json]
```

`--kind` は caveat / issue / decision / howto / insight です。同じタイトルの知見は 1 件にまとまり、`--obsolete` で廃止にできます。`collection` はコレクション全体を Markdown（既定）か JSON で出力します。

### コレクションの追加

ストア直下に `collections.json` を置くと、組み込みの「ナレッジ」に加えて、更新をためる先と表示を宣言的に追加・変更できます。ダッシュボードにはコレクションごとのタブが自動で表示されます。詳しくは [DESIGN.md §3.7](docs/DESIGN.md) を参照してください。

```json
[
  {"name": "knowledge", "sinks": [{"type": "markdown", "path": "KNOWLEDGE.md"}]},
  {"name": "decisions", "label": "決定ログ", "match": {"type": ["finding"], "kind": ["decision"]},
   "reduce": {"type": "log", "payload": "finding"}, "view": {"type": "table", "columns": ["title", "body", "reporters"]}}
]
```

親セッション・人間:

```bash
session-hub attention
session-hub status
session-hub log [<session_id>] [--heartbeat] [--tail N]
session-hub answer <session_id> --qid 4 --value 120
session-hub command <session_id> --cmd pause
session-hub export --out dashboard.html
```

`attention` は要対応だけを 1 行ずつ出します（親 LLM 向け）。`answer` と `command` は記録したうえで、子へ送る `[HUB/1]` 行を出力します。`export` はスナップショットを埋め込んだ静的 HTML を書き出します。

イベントを送るとき、状態が「親を起こすべきもの」（人間待ち・レビュー可・失敗・完了）に変わると、コマンドは `[HUB/1] ...` の 1 行を出力します。子はその行だけを `send_message` で親へ送ります。

## 環境変数

| 変数 | 用途 |
|---|---|
| `HUB_URL` | ハブサーバーの URL。設定すると子は push、親の `attention` などはサーバーから読む |
| `HUB_TOKEN` | ハブの認証トークン（サーバー・クライアント共通） |
| `HUB_STORE` | ストアのディレクトリ（サーバー、またはサーバーなしで使うとき） |
| `HUB_SESSION_ID` | 自セッション ID（未設定なら Claude Code の環境変数から取得） |
| `HUB_PARENT_SESSION_ID` | 親のセッション ID（子が `[HUB/1]` 行を送る宛先） |
| `HUB_STOP_GUARD` | `0` で Stop hook の確認を無効化 |
| `HUB_AUTOSTART` | `1` で、ローカルのハブサーバーが動いていなければセッション開始時に起動（`HUB_URL` が 127.0.0.1 / localhost のときだけ） |
| `HUB_OUTBOX` / `HUB_STATE_DIR` | outbox とローカル状態の置き場所（既定 `~/.cache/...`） |

## テスト

```bash
python3 -m unittest discover -s tests -v
```
