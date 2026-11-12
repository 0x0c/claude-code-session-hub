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

## 本番での構成

```
子セッション ──POST──► ハブサーバー（session-hub serve）──SSE──► ブラウザ
   └─ [HUB/1] 行だけ send_message ──► 親セッション ──GET snapshot──┘
```

### 1. ハブサーバーを起動する

子セッションから届く場所で起動します。localhost 以外で待ち受けるときはトークンが必須です。

```bash
HUB_STORE=/var/lib/session-hub HUB_TOKEN=<長いランダム文字列> session-hub serve --host 0.0.0.0 --port 8765
```

ブラウザでは最初に `http://<host>:8765/?token=<HUB_TOKEN>` を開きます（以後は cookie で認証され、URL からトークンは消えます）。
TLS は前段のリバースプロキシなどで終端してください。

### 2. 子セッションの環境を用意する

- 環境変数 `HUB_URL=https://<ハブのURL>` を設定する。
- ハブのホストをネットワーク許可リストに追加する。
- トークンは環境変数に平文で置かず、可能ならハブのホスト宛ての `Authorization: Bearer` ネットワークシークレットとして登録する（その場合 `HUB_TOKEN` は不要）。
- このリポジトリを Claude Code プラグインとして有効にする。

```text
/plugin marketplace add 0x0c/claude-code-session-hub
/plugin install session-hub@session-hub
```

プラグインを有効にすると、次が子セッションに入ります。`HUB_URL` も `HUB_STORE` もないセッションでは hook は何もしません。

| 種類 | 内容 |
|---|---|
| スキル `session-hub:report` | いつ・何を報告するか（子用） |
| スキル `session-hub:orchestrate` | 子の起動・`[HUB/1]` への対応・回答の仕方（親用） |
| SessionStart hook | `~/.local/bin/session-hub` を用意し、未登録なら `start` を促す 2 行を注入 |
| PostToolUse hook | TodoWrite / TaskCreate / TaskUpdate → タスク進捗と作業中タスク名を自動送信 |
| Stop hook | ターン終了ごとに heartbeat とトークン使用量を自動送信。作業中のまま終えようとしたら 1 回だけ報告を促す（`HUB_STOP_GUARD=0` で無効） |

### 3. 親から子を起動する

`create_session` の `append_system_prompt` に [prompts/child-append-system-prompt.md](prompts/child-append-system-prompt.md) の本文を、`{{PARENT_SESSION_ID}}` と `{{TITLE}}` を置き換えて渡します。

## コマンド早見表

子セッション（`HUB_URL` があれば push、なければ `HUB_STORE` に直接書く）:

```bash
session-hub start --title "作業名" --task-ref "#128" --task "設計=todo:S" --task "実装=todo:M"
session-hub report --phase test --summary "テスト追加中" --task "実装=done"
session-hub ask --kind decision --q "上限は?" --opt 60 --opt 120 --default 120 [--non-blocking]
session-hub pr --number 45 --ci pending --state waiting_ci
session-hub ready --self-review --tests --description
session-hub done --summary "PR #45"
session-hub fail --error "原因"
session-hub flush
```

`flush` は、届かずに outbox へ溜まったイベントを再送します。

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
| `HUB_OUTBOX` / `HUB_STATE_DIR` | outbox とローカル状態の置き場所（既定 `~/.cache/...`） |

## テスト

```bash
python3 -m unittest discover -s tests -v
```
