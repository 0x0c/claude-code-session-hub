# Session Hub 設計検討

親セッション（オーケストレーター）が複数の子セッションを走らせるとき、その状況を **少ないトークンで**、**一目で** 把握するための仕組みの検討。

> 実装状況: §8 のフェーズ 0・1・3・4 の大部分を実装済み（push 型ハブサーバー、時系列ビュー付きダッシュボード、報告スキルと hook）。
> 使い方は [README](../README.md)、用語は [付録 A 用語集](#付録-a-用語集) を参照。

## 0. 目的と設計原則

| 目的 | 具体的に知りたいこと |
|---|---|
| トークン節約 | 親が子のトランスクリプトを読まずに済む／不要な起床をしない |
| 人間の介入要否 | 判断・認証情報・権限・仕様確認など、人間待ちで止まっていないか |
| PRレビュー可否 | CI・自己レビュー・未解決事項が揃い、レビューに回してよいか |
| 稼働状況 | 今何をしているか、止まっていないか（ハートビート） |
| 残作業量 | 残りタスク数と規模、次の一手 |

原則:

1. **Pull 型が基本、Push は例外だけ** — 子の状態は共有ストアに書くだけ。親を起こす（=トークンを使う）のは「人間待ち」「レビュー可」「失敗」「完了」の遷移時のみ。
2. **集計と描画は LLM ではなくスクリプト** — ダッシュボード生成は決定的な処理でトークン 0。
3. **意味情報だけを LLM に書かせ、事実はスクリプトが拾う** — フェーズや質問文は子エージェントが書く。トークン数、コミット、PR/CI 状態、最終更新時刻は hook／スクリプトが自動取得する。
4. **固定スキーマ・列挙値・短文** — 自由記述は 1 行要約と質問文に限定。文字数上限を設ける。
5. **段階的開示** — 一覧（1行）→ 詳細（JSON 1件）→ トランスクリプト（リンク）。親は通常、一覧の「要対応」行しか読まない。
6. **自己申告を鵜呑みにしない** — 「レビュー可」は子の申告 + 機械的ゲート（CI 緑など）の AND で判定。

---

## 1. 記述する情報（ステータスレコード）

セッション 1 件につき 1 レコード（JSON）。`v` でスキーマのバージョンを持つ。

### 1.1 フィールド一覧

| グループ | フィールド | 書き手 | 説明 |
|---|---|---|---|
| 識別 | `v`, `session_id`, `parent_id`, `title`, `task_ref` | 起動時（親） | `task_ref` は Issue 番号やタスク ID |
| 場所 | `repo`, `branch`, `base` | 起動時 / hook | |
| 状態 | `state` | 子（CLI） | 下記の列挙値 |
| | `phase` | 子 | `plan` / `implement` / `test` / `fix` / `docs` / `self_review` など自由度の低い列挙 |
| | `summary` | 子 | 今何をしているか。**≤ 80 文字** |
| | `next` | 子 | 次の一手。≤ 80 文字 |
| 進捗 | `tasks.done`, `tasks.total`, `tasks.items[]` | 子 or hook | 各 item は `{t: "短い名前", s: "todo|doing|done|skip", size: "S|M|L"}` |
| | `remaining` | スクリプト | 未完了 item の size 合計から算出（S=1, M=3, L=8 など） |
| 人間待ち | `attention.kind` | 子 | `decision` / `clarification` / `credential` / `permission` / `review` / `external`(他チーム待ち等) |
| | `attention.question`, `attention.options[]`, `attention.default`, `attention.since` | 子 | 選択肢形式を推奨（回答が 1 語で済み、往復トークンが減る） |
| | `attention.blocking` | 子 | `true` なら完全停止、`false` なら既定値で進めつつ確認待ち |
| 阻害 | `blocked_on` | 子 | 他セッション ID や外部要因（`session:xxx`, `ci`, `upstream`） |
| PR | `pr.number`, `pr.url` | hook | |
| | `pr.ci` | スクリプト | `pending` / `pass` / `fail` / `none` |
| | `pr.mergeable`, `pr.unresolved_threads`, `pr.review` | スクリプト | GitHub から取得 |
| | `ready.self_review`, `ready.tests_added`, `ready.description` | 子 | 子の自己申告チェックリスト |
| | `ready.gate` | スクリプト | 下記 §4 の判定結果（`ready` / `not_ready:<理由>`） |
| コスト | `usage.input`, `usage.output`, `usage.cache_read`, `usage.cache_write`, `usage.cost_usd` | hook | トランスクリプト（`transcript_path`）の usage を合算 |
| | `usage.context_pct` | hook | コンテキスト使用率。圧縮間近の検知に使う |
| 健全性 | `heartbeat` | hook | 最終ターン終了時刻 |
| | `last_error` | 子 / hook | 直近の失敗（≤ 120 文字） |
| | `confidence` | 子 | `high` / `med` / `low`。低いものを人間が優先的に見る |
| 管理 | `seq`, `updated_at` | CLI | 単調増加。順序逆転・重複書き込みの排除 |
| | `links.session`, `links.artifacts[]` | hook | トランスクリプトや成果物への導線 |

### 1.2 `state` の列挙値と遷移

```
queued → planning → working ⇄ waiting_ci
                      │  ↑         │
                      ▼  │         ▼
              needs_human ─┘   review_ready → in_review → changes_requested ─┐
                      │                          │                       │
                      ▼                          ▼                       │
                   blocked                     done (merged)   ←── working ┘
任意の状態 → failed / abandoned
```

| state | 意味 | 親を起こすか |
|---|---|---|
| `queued` | 起動待ち | いいえ |
| `planning` / `working` | 作業中 | いいえ |
| `waiting_ci` | CI 待ち（子は手が空いている） | いいえ |
| `needs_human` | 人間の判断が必要 | **はい** |
| `blocked` | 他セッション・外部要因待ち | 長時間続けば（スクリプトが判断） |
| `review_ready` | レビューに出してよい（ゲート通過時のみ確定） | **はい** |
| `in_review` / `changes_requested` | レビュー中 / 指摘対応中 | 指摘時のみ |
| `done` | 完了 | **はい**（集約して 1 通） |
| `failed` / `abandoned` | 失敗・放棄 | **はい** |

### 1.3 レコード例

```json
{
  "v": 1, "session_id": "session_01ABC", "parent_id": "session_01PARENT", "seq": 42,
  "title": "認証APIのレート制限", "task_ref": "#128",
  "repo": "owner/app", "branch": "claude/rate-limit", "base": "main",
  "state": "needs_human", "phase": "implement", "confidence": "med",
  "summary": "Redis方式で実装中。上限値の決定待ち",
  "next": "回答後にミドルウェアへ組み込み、テスト追加",
  "tasks": {"done": 3, "total": 6, "items": [
    {"t": "設計", "s": "done", "size": "S"},
    {"t": "ミドルウェア", "s": "doing", "size": "M"},
    {"t": "テスト", "s": "todo", "size": "M"}
  ]},
  "remaining": 7,
  "attention": {"kind": "decision", "blocking": true, "since": "2026-11-12T03:10:00Z",
    "question": "1分あたりの上限は?", "options": ["60", "120", "300"], "default": "120"},
  "pr": {"number": null, "ci": "none"},
  "ready": {"self_review": false, "tests_added": false, "description": false, "gate": "not_ready:no_pr"},
  "usage": {"input": 182000, "output": 21000, "cache_read": 1450000, "cost_usd": 1.92, "context_pct": 38},
  "heartbeat": "2026-11-12T03:10:05Z", "updated_at": "2026-11-12T03:10:05Z"
}
```

---

## 2. やりとりの経路（トランスポート）の比較

| 経路 | 方向 | 親のトークン | 即時性 | 耐久性 | 人間からの見やすさ | 備考 |
|---|---|---|---|---|---|---|
| **A. Git の専用ブランチ**（orphan `hub/status`、1セッション1ファイル） | 子→ストア | 0 | 低（push 間隔） | 高（履歴=イベントログ） | 中 | どの環境でも動く。1ファイル/セッションで衝突をほぼ回避。push 失敗時は rebase リトライ |
| B. 作業ブランチにステータスファイルを同梱 | 子→ストア | 0 | 低 | 高 | 低 | PR の差分を汚すので非推奨 |
| **C. Artifact の共有 DB**（ArtifactData） | 子→ダッシュボード | 0 | 高 | 中 | **高**（そのまま Web ページ） | ダッシュボード自体を Artifact にすれば描画も即時。子セッションから同アカウントで書き込める前提 |
| D. `send_message`（子→親） | 子→親 | **毎回発生**（親のターンが走る） | 最高 | 低（会話内のみ） | 低 | エスカレーション専用にする |
| E. `send_message`（親→子） | 親→子 | 子側のみ | 最高 | 低 | — | 回答・指示（コマンド）用 |
| F. GitHub ラベル / PR 本文 / Issue コメント | 子→GitHub | 0 | 中 | 高 | 高（GitHub 上） | `hub:needs-human` などのラベルは GitHub 通知と連携できる。PR が無い段階では使えない |
| G. CCR API のポーリング（`get_session` の `status_bucket`、`list_events` の `kinds` 絞り込み） | 親が取得 | 小〜大 | 中 | — | — | 子の協力不要の「真値」。ただし MCP ツールなので LLM が呼ぶ必要があり、`list_events` は重い。`get_session` だけに限定すれば安い |
| H. ローカル実行時のトランスクリプト（`~/.claude/projects/**/*.jsonl`） | スクリプトが直接読む | 0 | 高 | 高 | — | ローカル並列実行時のみ。usage・最終ツール呼び出しなど事実情報が取れる |
| **I. ハブサーバーへの HTTP push**（`POST /api/events`） | 子→サーバー→ブラウザ | 0 | **最高**（受信即配信） | 高（サーバーがストアへ追記） | **高** | サーバーが子から到達可能である必要がある（§9） |

### 採用: push 型（I）を主経路に

当初は Git ストアをポーリングする案（A）を推奨していたが、**ダッシュボードの即時性**を優先して push 型に変更した。

- **子 → ハブ**: 子は状態が変わるたびに `session-hub` コマンドでハブサーバーへイベントを POST する（I）。
  サーバーは検証してストアに追記し、その場で接続中のブラウザへ SSE で配信する。**サーバーもブラウザもポーリングしない。**
- **届かないとき**: 子は送れなかったイベントを outbox（ローカル JSONL）に溜め、次の送信時に先に再送する。
- **耐久性**: ストアは追記のみの JSONL。必要なら A（Git）として共有・保管できる（補助機能 `--pull-every`）。
- **エスカレーション**: D を「親を起こすべき遷移」のときだけ使う（§3.3）。
- **回答・指示**: E。
- **死活の真値**: 親が必要なときだけ G の `get_session` を呼び、`status_bucket` と突き合わせる。
- **人間向け通知**: ダッシュボードのブラウザ通知、補助的に F のラベル。

## 3. プロトコル

### 3.1 構成要素

```
┌──────────── 子セッション ────────────┐
│ エージェント ── session-hub report ... ─┐   意味情報: state / phase / summary / 質問
│ Stop hook ───── session-hub hook stop ─┤   事実情報: heartbeat / トークン使用量（0 トークン）
│ PostToolUse ─── session-hub hook todo ─┤   TodoWrite 等 → 進捗（0 トークン）
│                                        ▼
│                    POST /api/events ─────────────┐   失敗時は outbox に保存し次回再送
│ 重要遷移時のみ ── send_message ─────────► 親（1 行）│
└────────────────────────────────────────┘          │
                                                     ▼
┌──────────── ハブサーバー（session-hub serve）─────────────┐
│ 検証 → seq / 時刻を採番 → ストアへ追記（events/*.jsonl）      │
│ → 状態を畳み込み、差分を SSE でブラウザへ即時配信             │
└───────────────┬─────────────────────────────────────┘
                ▼ GET /api/stream（SSE）          ▲ GET /api/snapshot
         ブラウザのダッシュボード              親: session-hub attention
```

- **イベントソーシング**: 状態は保存しない。追記のみのイベント列を畳み込んで毎回求める。
  イベント列そのものが時系列ビューの元データになり、「いつ何が変わったか」を後から完全にたどれる。
- **書き手ごとのファイル**: `events/<session_id>.jsonl`（子）と `events/<session_id>@parent.jsonl`（親の回答・指示）。
  1 ファイルの書き手は常に 1 人なので、Git で共有しても衝突しない。
- **時刻の採番**: ストア全体で単調増加するミリ秒時刻をサーバーが付ける。到着順＝表示順で一貫する。

### 3.2 子 → ハブ（`session-hub report` ほか）

子エージェントには「状態が変わったら 1 行の Bash を叩く」ことだけを課す（手順は `skills/session-hub-report/SKILL.md`）。

```bash
session-hub start --title "認証APIのレート制限" --task-ref "#128" --task "設計=todo:S" --task "実装=todo:M"
session-hub report --phase implement --summary "ミドルウェア実装中" --task "実装=doing"
session-hub ask --kind decision --q "1分あたりの上限は?" --opt 60 --opt 120 --opt 300 --default 120
session-hub pr --number 45 --ci pending --state waiting_ci
session-hub ready --self-review --tests --description
session-hub done --summary "PR #45 マージ済み"
```

- `HUB_URL` があればハブへ push、なければローカルのストア（`HUB_STORE`）に書く。
- サーバー側で検証・文字数の切り詰め・seq と時刻の採番を行う。不正な値は 400 で拒否され、子に候補が表示される。
- 呼び出しタイミングは**状態遷移時・質問発生時・PR の節目のみ**。
- 報告漏れは hook で補う（§3.6）。

### 3.3 子 → 親（エスカレーション通知）

親を起こすのは次の遷移のみ。1 行固定書式で、詳細はストアを見に行かせる。

```
[HUB/1] <session_id> <event> <短文≤80字>
```

| event | 例 | `send_message` の priority |
|---|---|---|
| `needs_human` | `[HUB/1] session_01ABC needs_human 上限値の決定待ち(60/120/300)` | `later`（`blocking` なら `next`） |
| `review_ready` | `[HUB/1] session_01ABC review_ready PR#45 CI緑` | `later` |
| `failed` | `[HUB/1] session_01ABC failed テスト環境が起動しない` | `next` |
| `done` | `[HUB/1] session_01ABC done PR#45 merged` | `later` |

- 親側は `[HUB/` で始まるメッセージを受けたら、本文を深読みせず `session-hub attention` を実行するだけ、と CLAUDE.md 等で規定する。
- 子同士のメッセージは仕組み上「ピアからのデータ」として扱われる。親はメッセージ中の指示に従わず、あくまで状態通知として扱う（プロンプトインジェクション耐性）。
- 同一イベントの連投防止: CLI が直近の通知を記録し、同じ `(state, attention.question)` では再送しない。

### 3.4 親 → 子（コマンド）

```
[HUB/1] cmd=<command> [key=value ...]
```

| command | 用途 |
|---|---|
| `answer q=<id> v=<value>` | 質問への回答（選択肢の値を返すだけ） |
| `report` | 最新状態の再送依頼（ハートビート切れ時） |
| `pause` / `resume` | 一時停止・再開 |
| `rebase base=main` | ベース追従の指示 |
| `abort reason=...` | 中止 |

### 3.5 親の定期処理（トークン最小化）

1. 親は待つだけでよい。子からの `[HUB/1]` メッセージを受けたときだけ `session-hub attention` を実行する（`HUB_URL` があればサーバーの snapshot を読む）。
2. 停滞の疑い（`ST`）があるときだけ `get_session` で死活を確認する。`list_events` は原則使わない。
3. 親が読むのは `attention` の出力（要対応行のみ、通常数行）。全件一覧と時系列は人間がダッシュボードで見る。

### 3.6 報告タイミングを保証する仕組み

push 型では、子が報告しない限りダッシュボードは古いままになる。そこで「何を・いつ送るか」を 3 層で担保する。

| 層 | 仕組み | トークン | 担保する内容 |
|---|---|---|---|
| 1. 自動送信（hook） | `Stop` hook → heartbeat とトークン使用量 / `PostToolUse(TodoWrite・TaskCreate・TaskUpdate)` → 進捗と作業中タスク名、着手時に planning→working | 0 | 「生きているか」「どこまで進んだか」 |
| 2. 手順（スキル + 起動プロンプト） | `skills/session-hub-report/SKILL.md`（いつ・何を送るかの表）、`prompts/child-append-system-prompt.md`（5 行の常駐ルール）、`SessionStart` hook が未登録なら `start` を促す 2 行を注入 | 小 | 意味情報（段階・質問・PR・完了） |
| 3. 終了時ガード | `Stop` hook が、最後に報告した状態が planning / working のまま、または未登録のままターンを終えようとしたら **1 回だけ** block して報告を促す（`stop_hook_active` で無限ループを防止、`HUB_STOP_GUARD=0` で無効化） | 1 ターン分（必要時のみ） | 「作業中のまま放置」の防止。ぐるぐる表示の正しさ |

- hook は `HUB_URL` / `HUB_STORE` が未設定なら何もしないので、プラグインを常時有効にしても他の作業に影響しない。
- hook はネットワーク失敗や例外でセッションを止めない（outbox に積むか、黙って終了コード 0）。
- 「最後に何を報告したか」は子のローカル状態（`~/.cache/session-hub/state-<id>.json`）で判断し、ガードのためにネットワークを使わない。

### 3.7 コレクション: 更新を「どこに・どうためて・どう見せるか」の抽象化

セッションごとの連絡とは別に、作業で判明した知見・注意点・決定事項のように**セッションをまたいで 1 か所にためたい情報**がある。
これを専用機能として作るのではなく、「受け取った更新をどこにためるか」を一般化した**コレクション**として扱う。

```
            ┌─ match ─┐   ┌── reduce ──┐   ┌── view ──┐
イベント列 ─┤ どれを   ├──►│ どうまとめる├──►│ どう見せる├──► ダッシュボードのタブ
（唯一の正）│ 集めるか │   │ log/latest/ │   │ cards/   │
            └─────────┘   │ aggregate   │   │ table    │──► sinks（Markdown / JSONL へ書き出し）
                          └────────────┘   └──────────┘
```

- **唯一の正はイベントストア。** コレクションはその上の投影（projection）で、定義を変えれば過去のイベントから作り直せる。
  保存先を増やしても、子の送り方（プロトコル）は変わらない。
- **定義は宣言的な JSON**（ストア直下の `collections.json`）。コードを書かずに追加・上書き・無効化できる。

| 要素 | 内容 | 例 |
|---|---|---|
| `match` | 集めるイベントの条件。`type`、`kind`、`tags_any`、`session`、`status` | `{"type": ["finding"], "kind": ["decision"]}` |
| `reduce` | まとめ方。`log`（時系列のまま）、`latest`（key ごとに最新 1 件）、`aggregate`（key ごとに 1 件へ統合） | 知見は `aggregate`、key は `key\|title`（明示キーがなければタイトル） |
| `view` | 表示形式。`cards`（`group_by` でグループ分け）、`table`（`columns` を指定） | 知見は種類別のカード |
| `sinks` | 追加の書き出し先。`markdown` / `jsonl`（ストア内のパス）。内容が変わったときだけ書き換える | `KNOWLEDGE.md` を自動更新してリポジトリや Wiki に載せる |

**aggregate の統合規則**: 本文などは最新の報告で上書き（空の値では上書きしない）、`tags` と `scope` は和集合、報告元はすべて残す。
同じ注意点に複数のセッションが気づくと 1 件にまとまり「2 セッション / 2 回報告」と表示される。重要度の自然な指標になる。
同じタイトルで `status: obsolete` を送ると「廃止」になり、既定の表示や `knowledge` 出力から外れる（履歴は残る）。

**組み込みコレクション「ナレッジ」**: 子が `session-hub learn` で送る `finding` イベントを集約する。

| `kind` | 表示名 | 記録するもの |
|---|---|---|
| `caveat` | 注意点 | 知らないとハマる罠 |
| `issue` | 未解決の問題 | 自分のタスク外で見つけて残した問題 |
| `decision` | 決定事項 | 決めたこと・回答をもらったこと（理由つき） |
| `howto` | 手順・ノウハウ | 再現・セットアップ・調査の手順 |
| `insight` | 知見 | 設計・性能・仕様について分かった事実 |

`finding` は `{kind, title(≤80), body(≤600, 改行可), tags[], scope, key, status}`。

**読み方（トークン節約）**: 子は着手前に `session-hub knowledge --scope <触る場所>` で関係するものだけを数行で読む。
親は新しい子を起動するときに、関係するものだけを `prompt` に添える。全件をコンテキストに入れることはしない。

**定義例**（`collections.json`）:

```json
[
  {"name": "knowledge", "sinks": [{"type": "markdown", "path": "KNOWLEDGE.md"}]},
  {"name": "decisions", "label": "決定ログ",
   "match": {"type": ["finding"], "kind": ["decision"]},
   "reduce": {"type": "log", "payload": "finding"},
   "view": {"type": "table", "columns": ["title", "body", "reporters", "last_ts"]}},
  {"name": "prs", "label": "PR 状況", "match": {"type": ["pr"]},
   "reduce": {"type": "latest", "key": ["session_id"]},
   "view": {"type": "table", "columns": ["session_id", "pr", "last_ts"]}}
]
```

### 3.8 ローカル運用（採用中の構成）

| 項目 | 内容 |
|---|---|
| 子の実行場所 | 手元の PC。人間が並行して起動する `claude` セッション、または親が `claude -p --append-system-prompt ...` でバックグラウンド起動するセッション |
| 共有設定 | `~/.claude/settings.json` の `env` に `HUB_URL=http://127.0.0.1:8765`、`HUB_STORE=~/.session-hub`、`HUB_AUTOSTART=1` |
| サーバー | 127.0.0.1 でのみ待ち受け（トークン不要）。`HUB_AUTOSTART=1` なら最初に始まったセッションの SessionStart hook が裏で起動する。二重起動はポートの取り合いで自然に防がれる |
| メッセージの配送 | 1. サーバーへ push（即時反映） 2. 届かなければ共有ストアへ直接書く 3. ストアも未設定なら outbox |
| 停止中のメッセージ | ストアに残るので失われない。サーバー起動時、次の push、または 30 秒ごとの再判定で画面に出る |
| 親への通知 | ローカルのセッション間メッセージ（使える場合）で `[HUB/1]` 行を送る。使えない場合はダッシュボードのブラウザ通知とタブのタイトル（要対応数）で人間が気づく |
| 導入 | `apm install 0x0c/claude-code-session-hub --target claude`（プロジェクト単位。スキルは `.claude/skills/`、hook は `.claude/settings.json`、本体は `apm_modules/`）または Claude Code プラグイン |
| 確認 | `session-hub doctor` |
| 注意 | Agent ツールのサブエージェントは親と同じセッション ID になるため、別セッションとしては表示されない（必要なら `--session` で固有 ID を渡す） |

## 4. 機械的に判定する項目（スクリプト側の責務）

### 4.1 レビュー可ゲート (`ready.gate`)

すべて満たしたときのみ `review_ready` を確定させる。満たさない場合は最初に失敗した理由を記録。

1. PR が存在し draft でない（または draft 解除予定）
2. CI が `pass`
3. `mergeable` が true（コンフリクトなし、ベースから大きく遅れていない）
4. 未解決のレビュースレッドが 0
5. `attention` が空
6. 子の自己申告 `ready.self_review` / `ready.tests_added` / `ready.description` が true
7. `tasks` に `todo` / `doing` が残っていない（`skip` は可）

### 4.2 停滞・異常の検知

| 条件 | 判定 |
|---|---|
| `state=working` かつ `heartbeat` が N 分以上前 | `stale?` — 親が `get_session` で確認 |
| `get_session.status_bucket=failed` だが `state≠failed` | 子が報告できずに落ちた |
| `needs_human` が M 時間以上 | 優先度を上げて表示 |
| `usage.context_pct` > 80 | 圧縮・分割を検討 |
| `usage.cost_usd` が予算超過 / 進捗に対して過大 | `cost_usd / tasks.done` で効率を表示 |
| `tasks` の残りが長時間減らない | ループ・迷走の疑い |

### 4.3 優先順位（ダッシュボードの並び順）

`needs_human(blocking)` > `failed` > `review_ready` > `stale?` > `needs_human(non-blocking)` > `changes_requested` > `blocked` > `working` > `waiting_ci` > `done`

---

## 5. ダッシュボード

### 5.1 出力形式

| 形式 | 用途 |
|---|---|
| `session-hub serve` のダッシュボード | 人間向け。push 受信と同時に反映（SSE） |
| `session-hub export --out dashboard.html` | スナップショットを埋め込んだ単体 HTML（共有・保存用、更新なし） |
| `GET /api/snapshot` | 機械向け JSON |
| `session-hub attention` | 親 LLM 向け。要対応のみ、1 件 1 行 |
| `session-hub log [<session_id>]` | ターミナルで時系列を追う |

### 5.2 画面構成

- **ヘッダー**: 接続状態（リアルタイム / 再接続中 / ポーリング）、セッション数、要対応数、作業中数、トークン合計、最終更新。
  要対応数はタブのタイトルにも `(3) Session Hub` の形で出る。ブラウザ通知（任意）で、人間待ち・レビュー可・失敗・完了・停滞への遷移を知らせる。
- **セッション一覧**（左）: 「要対応 / 作業中・待機 / 完了」に分け、§4.3 の優先順で並べる。
  各カードに状態バッジ、タスク進捗バー、残量、PR と CI、トークン・費用、最終更新、未回答の質問（選択肢と既定値、回答コマンド）。
  **手を動かしている状態（planning / working / changes_requested）のセッションにはスピナー（ぐるぐる）を表示する。**
  CI 待ち・ブロック・人間待ちなど「待っているだけ」の状態や、停滞の疑いがあるものには表示しない。
  自己申告だけでゲート（§4.1）を通っていない「レビュー可」は「レビュー条件未達」と未達理由を表示する。
- **タイムライン**（右）: 子から届いた報告を時系列でたどる。
  - **フィード**: 日付ごとにイベントを並べ、各行に時刻、セッション、種別、本文、そのイベントで変わったこと（状態 A→B、段階、タスク数、質問の解決）を表示。
    「詳細」で生のイベント JSON。新着はハイライトし、読んでいる途中で画面が動かないよう下にスクロール中は「新着 N 件」バーで知らせる。
    絞り込み: セッション、イベント種別、全文検索、heartbeat の表示（連続するものは 1 行にまとめる）、新しい順 / 古い順。
  - **スイムレーン**: セッションごとの横帯で、状態の推移を色の区間として表示。点はイベント（質問=橙、回答=青）。
    ホバーで詳細、クリックでフィードの該当行へ移動。人間待ちの長さや停滞が一目で分かる。
- **コレクションのタブ**（右パネル）: 定義されたコレクションごとにタブが自動で増える（例「ナレッジ (6)」）。
  `cards` はグループ（ナレッジなら種類）ごとのカードで、本文、タグ（クリックで検索）、対象、報告したセッションと回数、最終更新を表示する。
  報告元のセッション名をクリックすると、タイムラインの該当イベントへ移動する。セッション選択・全文検索・グループの絞り込み・廃止済みの表示切替ができる。
  push で届いた項目はその場でハイライトされる。
- **メッセージ受信時のグロー**: サブセッションからメッセージが届くと、そのセッションのカード、タイムラインの該当行、スイムレーンの帯、
  メッセージが入ったコレクションの項目を、遷移後の状態の色（人間待ち=橙、失敗=赤、レビュー可=緑など）で約 6 秒光らせる。
  画面が再描画されても途中から続き、連続して届いたときは最新のもので光り直す。heartbeat（hook の自動送信）は光らせない。
  動きを減らす設定（prefers-reduced-motion）では脈動せず、枠だけを表示する。
- スマホ幅（390px）でも横スクロールなしで読める。ライト / ダーク両対応。

### 5.3 `session-hub attention` の出力（親が読む分）

```
NH session_01ABC #128 decision q=4 "1分あたりの上限は?" [60|120*|300] 38m
FL session_04XYZ npm ci が ERESOLVE で失敗（peer 依存の衝突）
RR session_01DEF #131 PR#45 ci=pass CI 緑、自己レビュー済み
ST session_01GHI 47m since heartbeat
```

## 6. トークン節約のための追加策

| 策 | 効果 |
|---|---|
| 子にトランスクリプトを要約させず、状態は CLI 引数で渡す | 子の出力トークン削減 |
| 質問は選択肢 + 既定値で | 人間・親の往復を 1 語に |
| `attention.blocking=false` を活用（既定値で先へ進み、後で差し替え可能な判断） | 待ち時間の削減。結果として無駄な再開コストも減る |
| 親は `list_events` を原則使わない（使うなら `kinds` で `result` だけ） | 親の入力トークン削減 |
| 通知の集約（`done` は複数まとめて 1 通、など） | 親の起床回数削減 |
| 子のモデル・effort をタスク規模（`size`）で選ぶ | 単価の削減 |
| hook で usage を記録し、タスクあたりコストを可視化 | 高コストなパターンの発見 |
| Stop hook で「報告していなければ 1 回だけ報告を促す」 | 報告漏れ防止。ただし 1 ターン分のコストがかかるので条件付き（状態が変わったのに未報告の場合のみ） |

---

## 7. 実装構成

```
claude-code-session-hub/
  session_hub/            Python パッケージ（標準ライブラリのみ）
    schema.py             スキーマ定義・検証・畳み込み・レビュー可ゲート
    store.py              追記型イベントストア（書き手ごとの JSONL、単調時刻、Git 同期）
    core.py               記録処理とエスカレーション判定（CLI とサーバーで共通）
    client.py             push クライアント（outbox による再送）
    server.py             ハブサーバー（POST 受信、SSE 配信、トークン認証）
    view.py               ダッシュボード / attention / log / knowledge 用のデータ組み立て
    collections.py        コレクション（match / reduce / view / sinks）の定義と投影
    hooks.py              Claude Code hook の処理（session-start / stop / todo）
    local_state.py        子側のローカル状態（最後の報告状態、タスク ID 対応）
    usage.py              トランスクリプトからのトークン集計
    cli.py                session-hub コマンド
    templates/dashboard.html
  bin/session-hub         インストール不要のラッパー
  .claude-plugin/         Claude Code プラグイン定義（plugin.json, marketplace.json）
  apm.yml                 APM 用のメタデータのみ（プラグイン構成のまま APM でも配布するため .apm/ や依存は置かない）
  hooks/hooks.json        プラグインの hook 設定
  skills/session-hub-report/       子セッション用スキル（いつ・何を報告するか）
  skills/session-hub-orchestrate/  親セッション用スキル（起動・応答・確認）
  prompts/child-append-system-prompt.md   create_session に渡す短い常駐ルール
  scripts/demo.py         デモデータと疑似 push
  tests/
```

## 8. 段階的な進め方

| フェーズ | 内容 | 状況 |
|---|---|---|
| 0 | スキーマ + 報告コマンド + ストア + 一覧 | 実装済み |
| 1 | Stop hook で usage・heartbeat 自動記録、TodoWrite 連携 | 実装済み |
| 2 | GitHub から PR / CI / 指摘数を自動取得してゲート判定 | 判定ロジックは実装済み。取得は `session-hub pr` での手動記録のみ |
| 3 | エスカレーション通知と親の運用ルール | 実装済み（`[HUB/1]` 行の出力、orchestrate スキル） |
| 4 | リアルタイムダッシュボードと時系列ビュー | 実装済み（push + SSE） |
| 5 | 停滞検知・予算アラート・集約通知 | 停滞検知のみ実装済み |
| 6 | コレクション（ナレッジなど、更新の蓄積先の抽象化） | 実装済み（組み込み「ナレッジ」、collections.json、Markdown / JSONL sink） |

## 9. 未決事項

1. **ハブサーバーの置き場所**: **当面はローカル運用に決定。** サブセッションを手元の PC で動かし、全セッションで `HUB_STORE` を共有する。
   ハブサーバーは `127.0.0.1` でのみ待ち受け、子は `HUB_URL=http://127.0.0.1:8765` へ push する（PC を外部に公開しない）。
   サーバーが止まっている間は共有ストアへ直接書き、サーバーが起動するか次の push で画面に出る（§3.8）。
   クラウドの子セッションを使う場合の候補（常設サーバー、Artifact の共有 DB）は将来の検討事項として残す。
   どちらの場合も子の環境のネットワーク許可リストにそのホストを追加し、トークンは環境変数ではなくネットワークシークレットとして登録するのが望ましい。
2. **実行環境**: 子はクラウドセッション（`create_session`）中心か、ローカルの並列実行も含むか。ローカルのみなら `HUB_STORE` を共有するだけでよい。
3. **GitHub 情報の自動取得**（フェーズ 2）: サーバーから GitHub API を叩くか、親が取得して `session-hub pr` で記録するか。
4. **自動化の範囲**: `review_ready` 時に PR の draft 解除やレビュアー割り当てまで自動で行うか。
5. **予算**: セッション単位・全体のコスト上限と、超過時の挙動（通知のみ / 停止）。費用は今はトークン数のみ自動記録（金額は `--cost` で任意）。
6. **ナレッジの整理**: 似ているが表現の違う知見は別の項目になる。定期的に親（または人間）が `--key` で統合・`--obsolete` で廃止する運用でよいか、類似度でまとめる仕組みが要るか。
7. **ハブからサブセッションへの指示**: 作業中のサブセッションには hook 経由で届けられるが、止まっているセッションは起こせない（親か人間の `send_message` が必要）。実装しないことに決定済み。親が `session-hub answer` / `command` で記録し、出力行を `send_message` で送る現行の方式のままとする。
8. **規模**: 受信のたびに全イベントから状態を作り直している。数千イベント程度までは問題ないが、それを超えるなら差分更新にする。

---

## 付録 A 用語集

### 登場人物・構成要素

| 用語 | 意味 |
|---|---|
| 親セッション（オーケストレーター） | 子セッションを起動し、質問への回答やレビュー依頼などの判断をするセッション。ダッシュボードを見る人間を含めて「親側」と呼ぶこともある |
| 子セッション / サブセッション | 親から作業を任されて動くセッション。自分の状況をハブへ報告する |
| ハブ / ハブサーバー | `session-hub serve` で動くサーバー。子からの報告を受け取り、保存し、ブラウザへ配信する |
| ストア | イベントを保存するディレクトリ（`HUB_STORE`、既定 `.hub`）。`events/*.jsonl` が本体 |
| ダッシュボード | ハブが配信する Web 画面。セッション一覧とタイムラインからなる |
| `session-hub` | 本ツールのコマンド。子の報告、親の確認・回答、サーバー起動、hook の処理をすべて担う |
| プラグイン | 本リポジトリを Claude Code のプラグインとして読み込んだもの。スキル・hook・コマンドをまとめて子セッションに配る |

### データとプロトコル

| 用語 | 意味 |
|---|---|
| メッセージ | サブセッションからハブへ届く更新 1 件。保存されると 1 件のイベントになる。ダッシュボードは受信すると関係する表示をグローで一定時間光らせる。親への `send_message`（[HUB/1] 行）は「エスカレーション通知」と呼んで区別する |
| グロー | メッセージを受信したときの強調表示。送り主のセッションカード、タイムラインの該当行、スイムレーンの帯、そのメッセージが入ったコレクションの項目を、遷移後の状態の色で約 6 秒光らせる（heartbeat は対象外） |
| イベント | 子や親が送る 1 件の報告（JSON 1 行）。種類は start / report / ask / answer / command / ready / pr / heartbeat / done / fail |
| ステータス（ステータスレコード） | あるセッションの「今の状態」。イベント列を古い順に適用（畳み込み）して求める。保存はしない |
| 畳み込み（fold） | イベントを 1 件ずつ順に当てはめて最新の状態を計算すること |
| イベントソーシング | 状態ではなく「起きた出来事」を追記で保存し、状態は出来事から計算する設計。時系列をたどれるのはこのため |
| 追記のみ（append-only） | 書いたイベントを後から書き換えない・消さない保存方式 |
| 書き手（writer） | イベントファイルの持ち主。子自身は `<id>.jsonl`、親の回答・指示は `<id>@parent.jsonl` |
| seq | 書き手ファイルごとの連番。イベント ID は `<ファイル名>#<seq>`（例 `session_01ABC#3`） |
| state | セッションの状態（§1.2 の 12 種類）。例: working、needs_human、review_ready |
| phase | 作業段階。plan / implement / test / fix / docs / self_review など |
| attention | 人間・親への質問。種類（kind）、質問文、選択肢、既定値、停止中かどうか（blocking）を持つ |
| qid | 質問の番号。回答（answer）がどの質問に対するものかを示す |
| blocking / non-blocking | 回答が来るまで止まっている質問 / 既定値で先に進めている質問 |
| tasks / progress / 残量 | タスク一覧と、完了数・総数。残量は未完了タスクの規模（S=1, M=3, L=8）の合計 |
| heartbeat | 「まだ生きている」ことを示す自動イベント。トークン使用量も運ぶ |
| usage | トークン使用量（input / output / cache_read / cache_write）と任意で費用・コンテキスト使用率 |
| `HUB/1` | 親子間メッセージの書式とその版。`[HUB/1] <id> <state> <短文>`（子→親）、`[HUB/1] cmd=<命令> ...`（親→子） |
| エスカレーション（通知） | 親を起こすべき遷移（人間待ち・レビュー可・失敗・完了）のときにだけ、子が親へ 1 行送ること |
| コマンド（cmd） | 親から子への指示。answer / report / pause / resume / rebase / abort |

### 判定と表示

| 用語 | 意味 |
|---|---|
| 要対応 | 人間か親が何かすべきセッション。人間待ち・失敗・レビュー可・停滞の疑い |
| レビュー可ゲート | 「レビューに出してよいか」の機械判定。PR あり、CI 成功、コンフリクトなし、未解決の指摘 0、未回答の質問なし、自己チェック済み、残タスクなし（§4.1） |
| レビュー条件未達 | 子は「レビュー可」と申告したが、ゲートを通っていない状態。未達の理由を表示する |
| 自己申告 / 自己チェック | 子が `session-hub ready` で申告する、自己レビュー・テスト追加・PR 説明の完了 |
| 停滞（stale） | 作業中のはずなのに一定時間（既定 30 分）報告がないこと。落ちている可能性がある |
| 優先度 | ダッシュボードの並び順（§4.3）。人間待ち（停止中）が最上位 |
| スピナー（ぐるぐる） | 子が手を動かしている状態（計画中・作業中・修正対応中）を示す回転アイコン |
| フィード | タイムラインの表示形式の一つ。イベントを時刻順に並べた一覧 |
| スイムレーン | タイムラインの表示形式の一つ。セッションごとの横帯に状態の推移を色で示す |

### 通信と仕組み

| 用語 | 意味 |
|---|---|
| push 型 | 子が変化のたびにハブへ送り、ハブがすぐ画面へ送る方式。受け手が定期的に見に行く「ポーリング」の反対 |
| ポーリング | 一定間隔で変化がないか確認しに行く方式。本ツールでは補助機能（`--watch-files`、`--pull-every`、ブラウザの SSE が使えないときの代替）にだけ使う |
| SSE（Server-Sent Events） | サーバーからブラウザへ、接続を張ったまま次々とデータを送る仕組み。ダッシュボードの即時反映に使う |
| snapshot / update | SSE で送るデータ。接続直後に全体（snapshot）、以後は変化分（update） |
| outbox | ハブに届かなかったイベントを子の手元に溜めるファイル。次の送信時に先に再送する |
| `HUB_URL` / `HUB_TOKEN` | 子・親が使うハブの URL と認証トークン |
| `HUB_STORE` | ストアのディレクトリ。`HUB_URL` がないときは子もここへ直接書く |
| `HUB_SESSION_ID` | 自セッションの ID。未設定なら Claude Code の環境変数から求める |
| hook | Claude Code が特定のタイミングで自動実行するコマンド。本ツールでは SessionStart・PostToolUse・Stop を使う |
| SessionStart hook | セッション開始時に動く。コマンドを使えるようにし、未登録なら登録を促す短い文をコンテキストへ入れる |
| PostToolUse hook | ツール実行後に動く。TodoWrite などのタスク操作を進捗としてハブへ送る |
| Stop hook | ターン終了時に動く。heartbeat を送り、作業中のまま終えようとしていたら 1 回だけ報告を促す |
| スキル | 必要なときに読み込まれる手順書。子用 `session-hub-report`、親用 `session-hub-orchestrate` |
| `append_system_prompt` | `create_session` で子に常に効かせる追加指示。本ツールでは 5 行の報告ルールを渡す |
| `send_message` | セッション間でメッセージを送る機能。届くと受け手のターンが動くのでトークンを使う。エスカレーションと指示にだけ使う |
| `get_session` / `status_bucket` | セッションの状態を取得する機能と、その大まかな状態（working / blocked / failed など）。停滞の確認に使う |
| `list_events` | 子のトランスクリプトを読む機能。重いので原則使わない |

### ナレッジとコレクション

| 用語 | 意味 |
|---|---|
| コレクション | 受け取った更新を「どれを集め（match）、どうまとめ（reduce）、どう見せ（view）、ほかにどこへ書き出すか（sinks）」の定義と、その結果。イベントストアの投影 |
| 投影（projection） | 保存済みのイベント列から、目的に合わせた形のデータを計算して作ること。元のイベントは変えない |
| match | コレクションに入れるイベントの条件 |
| reduce | まとめ方。log（時系列のまま）/ latest（キーごとに最新 1 件）/ aggregate（キーごとに 1 件へ統合） |
| key | reduce で「同じもの」とみなす単位。ナレッジでは明示キー、なければタイトル（空白・大文字小文字を無視） |
| view | 表示形式。cards（グループ分けしたカード）/ table（表） |
| sink | コレクションの追加の書き出し先（Markdown / JSONL ファイル） |
| `collections.json` | ストア直下に置くコレクション定義。組み込みの追加・上書き・無効化に使う |
| ナレッジ | 組み込みコレクション。サブセッションが作業で判明した知見・注意点などを 1 か所に集める |
| finding | ナレッジに入るイベントの種類。`session-hub learn` で送る |
| kind（finding の） | 知見の種類。caveat（注意点）/ issue（未解決の問題）/ decision（決定事項）/ howto（手順）/ insight（知見） |
| scope | 知見が関係する場所（パス、モジュール、サービス名）。`knowledge --scope` で関係するものだけを読むのに使う |
| obsolete（廃止） | もう当てはまらなくなった知見。表示と `knowledge` 出力から外れるが履歴は残る |
| 報告元（reporters） | その項目を報告したセッションの一覧。複数あるほど多くの作業者が遭遇したことを示す |
