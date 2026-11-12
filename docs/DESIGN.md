# Session Hub 設計検討

親セッション（オーケストレーター）が複数の子セッションを走らせるとき、その状況を **少ないトークンで**、**一目で** 把握するための仕組みの検討。

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

### 推奨: ハイブリッド

- **状態の保存先**: A（Git orphan ブランチ）を正とし、C（Artifact DB）をオプションのミラー／表示層にする。Git は環境を選ばず監査ログにもなる。
- **エスカレーション**: D を「親を起こすべき遷移」のときだけ使う（§3.3）。
- **回答・指示**: E。
- **死活の真値**: 親が定期実行時に G の `get_session` だけを呼び、`status_bucket` を突き合わせる（子が報告を忘れた／落ちたケースの検知）。
- **人間向け通知**: F のラベルを補助的に（PR がある場合）。

---

## 3. プロトコル

### 3.1 構成要素

```
┌─────────── 子セッション ───────────┐
│ エージェント ── hub report ...  ─┐ │   (意味情報: state/phase/summary/質問)
│ Stop hook ──── hub autosync ───┤ │   (事実情報: usage/heartbeat/branch/PR)
│                                ▼ │
│                     .hub/status.json ── git push ──► hub/status ブランチ
│ 重要遷移時のみ ── send_message ──────────────────► 親 (1行)
└──────────────────────────────────┘
┌─────────── 親セッション / 人間 ──────┐
│ hub sync    : hub/status を fetch + GitHub(PR/CI) を取得 + 判定   │
│ hub render  : dashboard.md / dashboard.html / summary.json 生成   │
│ hub attention: 要対応行だけを数行で出力（親 LLM が読むのはこれだけ）│
│ 回答: send_message(子, "[HUB/1] answer q=1 v=120")               │
└──────────────────────────────────┘
```

### 3.2 子 → ストア（`hub report`）

子エージェントには「状態が変わったら 1 行の Bash を叩く」ことだけを課す。

```bash
hub report --state working --phase implement --summary "ミドルウェア実装中" --next "テスト追加" --task "ミドルウェア=doing"
hub ask --kind decision --q "1分あたりの上限は?" --opt 60 --opt 120 --opt 300 --default 120 --blocking
hub ready --self-review --tests --description
hub done --summary "PR #45 マージ済み"
```

- CLI が `seq` 採番、文字数切り詰め、スキーマ検証、ファイル書き込み、（間引きつつ）git push を行う。
- 呼び出しタイミング: **状態遷移時・タスク完了時・質問発生時のみ**。ツール呼び出しごとには叩かない。
- `tasks` は Claude Code のタスクリスト（TaskCreate/TaskUpdate 等）が使われていれば hook 側でそこから同期し、子が二重に書く手間を省く案も検討（保存場所はバージョン依存のため実装時に確認）。

### 3.3 子 → 親（エスカレーション・メッセージ）

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

- 親側は `[HUB/` で始まるメッセージを受けたら、本文を深読みせず `hub sync && hub attention` を実行するだけ、と CLAUDE.md 等で規定する。
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

1. スクリプトのみ: `hub sync && hub render`（cron やローカルでのループ、トークン 0）。
2. LLM が関与するのは「エスカレーション受信時」と「低頻度の死活確認（例: 30 分ごとに `get_session` × 稼働中の子の数）」だけ。
3. 親が読むのは `hub attention` の出力（要対応行のみ、通常数行）。全件一覧は人間がダッシュボードで見る。

---

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
| `summary.json` | 機械向け。他ツール連携、Artifact DB への投入 |
| `dashboard.md` | Git 上でそのまま見られる。hub/status ブランチの README として置けば GitHub で閲覧可 |
| `dashboard.html` | 単体 HTML。必要なら Artifact として公開（共有 DB 読み込み型にすればリアルタイム化） |
| `hub attention` (stdout) | 親 LLM 向け。要対応のみ、1件1行 |

### 5.2 一覧の表示イメージ

```
要対応 (2)
 ⚠ needs_human  認証APIのレート制限   #128  上限値は? [60|120*|300]          38分前
 ✓ review_ready ログ出力の構造化      PR#45 CI✓ 指摘0                         5分前
作業中 (3)
 ▶ working      検索インデックス刷新   ▓▓▓▓▓░░░ 5/8 残≈6  テスト追加中       2分前   $3.10
 ⏳ waiting_ci   依存更新              PR#47 CI…                               9分前   $0.40
 ? stale        画像リサイズ           ▓▓░░░░ 2/6       最終更新 47分前              $1.20
完了 (4)  合計 $12.40 / 入力 3.1M / 出力 0.4M
```

### 5.3 `hub attention` の出力（親が読む分）

```
NH session_01ABC #128 decision "1分あたりの上限は?" [60|120*|300] 38m
RR session_01DEF PR#45 ci=pass threads=0
ST session_01GHI 47m since heartbeat
```

---

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

## 7. 実装構成案

```
claude-code-session-hub/
  hub/                    # Python パッケージ（標準ライブラリのみで動かす）
    schema.py             # スキーマ定義・検証・切り詰め
    store_git.py          # hub/status ブランチの読み書き（fetch/rebase/push リトライ）
    store_artifact.py     # (任意) Artifact DB 用の書き出し
    github.py             # PR / CI / review threads の取得
    gate.py               # §4 の判定
    render.py             # md / html / json / attention
    cli.py                # report, ask, ready, done, sync, render, attention
  hooks/
    stop_autosync.sh      # transcript_path から usage 合算、heartbeat 更新
  templates/
    dashboard.html
  docs/
    DESIGN.md             # 本書
    PROTOCOL.md           # 子・親に読ませる短い規約（CLAUDE.md から参照）
  schema/status.v1.json   # JSON Schema
```

子・親へのルールは `PROTOCOL.md` に短くまとめ、`create_session` の `append_system_prompt` で渡す（子に長い説明を毎回読ませない）。

## 8. 段階的な進め方

| フェーズ | 内容 | 完了条件 |
|---|---|---|
| 0 | スキーマ + `hub report/ask/done` + Git ストア + `dashboard.md` | 手動で 2〜3 セッションの状態が一覧できる |
| 1 | Stop hook で usage・heartbeat 自動記録 | 子が何もしなくてもコストと最終更新が出る |
| 2 | GitHub 連携とレビュー可ゲート | `review_ready` が機械判定される |
| 3 | エスカレーション通知と親の運用ルール | 親が `[HUB/1]` を受けたときだけ動く |
| 4 | HTML / Artifact ダッシュボード | ブラウザ・スマホで閲覧できる |
| 5 | 停滞検知・予算アラート・集約通知 | §4.2 が自動で出る |

## 9. 未決事項

1. **正となるストア**: Git orphan ブランチ（推奨）か、Artifact DB か。後者は即時性とスマホでの見やすさが勝るが、ローカル実行や他ツールとの連携は Git の方が楽。
2. **実行環境**: 子はクラウドセッション（`create_session`）中心か、ローカルの並列実行も含むか。ローカルを含むならトランスクリプト直読み（§2-H）が使える。
3. **GitHub 情報の取得手段**: スクリプトから `gh` / GitHub API を直接叩けるか（クラウド環境では制限があるため、親が MCP で取得して渡す形になる可能性）。
4. **自動化の範囲**: `review_ready` 時に PR の draft 解除やレビュアー割り当てまで自動で行うか。
5. **予算**: セッション単位・全体のコスト上限と、超過時の挙動（通知のみ / 停止）。
