"""What the design system page says beyond the dashboard's own stylesheet.

scripts/design_system.py combines this text with session_hub/templates/dashboard.html. The page is
written in Japanese. Values never live here: they come from the stylesheet.
"""

# What each design token is for. A token of the stylesheet without an entry stops the build.
USAGE = {'bg': 'ページの地。コードブロックと検索欄の地にも使う。',
 'panel': 'パネルとヘッダーの地。',
 'ink': 'bg・panel・hover の上の本文。',
 'muted': 'bg・panel・hover の上の補助文字（時刻、メタ情報、ラベル）。',
 'line': '罫線、枠線、進捗バーの溝。装飾用で、意味は担わせない。',
 'hover': 'ホバー中と選択中の行の地。',
 'accent': '選択中のタブ、押下中のボタン、新着バー。',
 's-needs': '状態：人間待ち、要修正。',
 's-review': '状態：レビュー可。',
 's-fail': '状態：失敗。危険な操作のボタンにも使う。',
 's-stale': '状態：停滞。',
 's-work': '状態：作業中、計画中。進捗バーにも使う。',
 's-wait': '状態：CI待ち、レビュー中。',
 's-block': '状態：ブロック。',
 's-done': '状態：完了、中止。',
 's-queue': '状態：待機。未知の状態の既定色。',
 'flash': '更新直後の一瞬の地。',
 'g-action': 'グループ見出し「要対応」の塗り。',
 'g-active': 'グループ見出し「作業中・待機」の塗り。',
 'g-done': 'グループ見出し「完了」の塗り。',
 'on-fill': '塗り（s-*・g-*・accent）の上の文字。',
 'shade': 'グリッドの詳細パネルが落とす影。',
 'space-1': 'バッジの上下。',
 'space-2': '行間の微調整。',
 'space-4': 'チップ同士の間隔。',
 'space-6': '小さな部品の間隔、質問ボックスの上下。',
 'space-8': '行内の部品の間隔、バッジの左右。',
 'space-10': 'カードの上下の余白。',
 'space-12': 'フィードや表の下端の余白。',
 'space-14': 'パネル内の左右の余白。',
 'space-16': 'ページの余白、パネル間の間隔。',
 'space-24': '空の表示の上下。',
 'radius-xs': '進捗バー。',
 'radius-sm': 'チップ、選択肢、グループ見出し。',
 'radius-md': 'ボタン、入力欄、質問ボックス。',
 'radius-lg': 'グリッドのカード、要対応の枠、ナレッジのカード。',
 'radius-xl': 'パネル。',
 'radius-pill': '状態バッジ、新着バー。',
 'fs-title': '製品名。',
 'fs-body': '本文。',
 'fs-body-sm': '要約、パネル見出し。',
 'fs-meta': 'メタ情報、グループ見出し。',
 'fs-label': 'バッジ、チップ。',
 'fw-normal': '既定。',
 'fw-strong': '強調。'}

# (name, group, preview height, markup, what it is and what to pass, rules)
COMPONENTS = [('GroupHeading',
  'Sessions',
  210,
  '<button class="project" type="button" aria-expanded="true"><span class="chev" aria-hidden="true">▸</span><span class="pname"><span '
  'class="group-badge" style="--group-color:var(--g-action)">要対応</span></span><span class="count">4</span></button><button class="project" '
  'type="button" aria-expanded="true"><span class="chev" aria-hidden="true">▸</span><span class="pname"><span class="group-badge" '
  'style="--group-color:var(--g-active)">作業中・待機</span></span><span class="count">1</span></button><button class="project" type="button" '
  'aria-expanded="false"><span class="chev" aria-hidden="true">▸</span><span class="pname"><span class="group-badge" '
  'style="--group-color:var(--g-done)">完了</span></span><span class="count">2</span></button><button class="project" type="button" '
  'aria-expanded="false"><span class="chev" aria-hidden="true">▸</span><span class="pname">アーカイブ済み</span>'
  '<span class="count">3</span></button>',
  'セッション一覧の状態別の見出しで、全体が開閉ボタンです。文言、件数、`g-*`、開閉状態を渡します。',
  'ラベルだけを `g-*` で塗り、白文字を載せます。「アーカイブ済み」は塗らず、文字だけにします。配下のセッション名より大きくしません。空のグループは出しません。'),
 ('ProjectHeading',
  'Sessions',
  120,
  '<button class="project" type="button" aria-expanded="true"><span class="chev" aria-hidden="true">▸</span><span class="pname">api</span><span '
  'class="count">2</span></button><button class="project" type="button" aria-expanded="false"><span class="chev" aria-hidden="true">▸</span><span '
  'class="pname">プロジェクトなし</span><span class="count">1</span></button>',
  'プロジェクト別の見出しで、全体が開閉ボタンです。名前、件数、開閉状態を渡します。',
  '状態の見出しと違い、ラベルを塗りません。'),
 ('ActionSection',
  'Sessions',
  220,
  '<section class="action-section"><button class="project" type="button" aria-expanded="true"><span class="chev" aria-hidden="true">▸</span><span '
  'class="pname"><span class="group-badge" style="--group-color:var(--g-action)">要対応</span></span><span class="count">1</span></button><div '
  'class="cards"><div class="cardwrap "><div class="card "><div class="row1"><span class="dot" style="background:var(--s-work)"></span><span '
  'class="title">認証APIのレート制限</span><span class="badge" style="background:var(--s-needs)">人間待ち</span></div><div '
  'class="meta"><span>#128</span><span>1/4 残≈7</span><span><a class="pr" href="https://example.com/pull/45">PR#45</a> '
  'CI:pending</span><span>30分前</span></div><div class="summary">Redis のスライディングウィンドウ方式で実装開始</div><div class="progress"><i '
  'style="width:25%"></i></div></div></div></div></section>',
  '対応が要るセッションを囲む枠。見出しとカードを渡します。',
  '一覧の先頭に1つだけ置きます。'),
 ('SessionCard',
  'Sessions',
  340,
  '<div class="cardwrap "><div class="card "><div class="row1"><span class="dot" style="background:var(--s-work)"></span><span '
  'class="title">認証APIのレート制限</span><span class="badge" style="background:var(--s-needs)">人間待ち</span></div><div '
  'class="meta"><span>#128</span><span>1/4 残≈7</span><span><a class="pr" href="https://example.com/pull/45">PR#45</a> '
  'CI:pending</span><span>30分前</span></div><div class="summary">Redis のスライディングウィンドウ方式で実装開始</div><div class="progress"><i '
  'style="width:25%"></i></div></div></div><div class="cardwrap "><div class="card selected"><div class="row1"><span class="dot" '
  'style="background:var(--s-work)"></span><span class="title">認証APIのレート制限</span><span class="badge" '
  'style="background:var(--s-needs)">人間待ち</span></div><div class="meta"><span>#128</span><span>1/4 残≈7</span><span><a class="pr" '
  'href="https://example.com/pull/45">PR#45</a> CI:pending</span><span>30分前</span></div><div class="summary">Redis のスライディングウィンドウ方式で実装開始</div><div '
  'class="progress"><i style="width:25%"></i></div></div></div>',
  '1つのサブセッションの現状を示すカード。利用側は名前、状態、メタ情報、要約、進捗を渡します。',
  '名前は1行で省略します。PRのURLがあればリンクにします。完了したセッションには進捗バーを出しません。'),
 ('AskBox',
  'Sessions',
  140,
  '<div class="ask"><div><b>Q4 decision（停止中）: </b>1分あたりのリクエスト上限は?</div><div class="opts"><span class="opt">60</span><span class="opt '
  'def">120</span><span class="opt">300</span></div></div>',
  '人間の回答を待つ質問。質問文と選択肢を渡します。',
  '既定の選択肢だけを `s-needs` の枠と太字で示します。'),
 ('StateBadge',
  'Status',
  70,
  '<div style="display:flex;gap:6px;flex-wrap:wrap"><span class="badge" style="background:var(--s-needs)">人間待ち</span><span class="badge" '
  'style="background:var(--s-review)">レビュー可</span><span class="badge" style="background:var(--s-fail)">失敗</span><span class="badge" '
  'style="background:var(--s-stale)">停滞?</span><span class="badge" style="background:var(--s-work)">作業中</span><span class="badge" '
  'style="background:var(--s-wait)">CI待ち</span><span class="badge" style="background:var(--s-block)">ブロック</span><span class="badge" '
  'style="background:var(--s-done)">完了</span><span class="badge" style="background:var(--s-queue)">待機</span></div>',
  '状態を示す小さなバッジ。状態の文言と `s-*` を渡します。',
  '1枚のカードに1つだけ置きます。'),
 ('Chip',
  'Status',
  60,
  '<div style="display:flex;gap:4px"><span class="chip">implement</span><span class="chip">タスク 1/2 → 2/2</span></div>',
  '補足を示す枠だけのラベル。文言を渡します。',
  '状態には使いません。'),
 ('ProgressBar', 'Status', 50, '<div class="progress"><i style="width:40%"></i></div>', 'タスクの進み具合。0〜100% の幅を渡します。', '数値はメタ情報に併記します。'),
 ('ConnectionStatus',
  'Status',
  60,
  '<div style="display:flex;gap:16px"><span class="conn live"><span class="dot"></span>リアルタイム（push 受信中）</span><span class="conn retry"><span '
  'class="dot"></span>再接続中</span></div>',
  'ハブとの接続状態。状態の文言を渡します。',
  'ヘッダーに1つ置きます。'),
 ('Button',
  'Controls',
  60,
  '<div style="display:flex;gap:8px"><button class="iconbtn">テーマ</button><button class="iconbtn" aria-pressed="true">通知</button><button '
  'class="iconbtn danger" style="margin-left:0">セッションを削除</button></div>',
  '枠だけの小さなボタン。動作を表す文言を渡します。',
  '削除など取り消せない操作だけ `danger` にします。'),
 ('Tabs',
  'Controls',
  60,
  '<div class="tabs"><button aria-selected="true">フィード</button><button aria-selected="false">スイムレーン</button><button aria-selected="false">ナレッジ '
  '(5)</button></div>',
  '表示の切り替え。タブの文言と選択中の1つを渡します。',
  '選択中だけ `accent` で塗ります。'),
 ('LayoutToggle',
  'Controls',
  60,
  '<span class="seg" style="margin-left:0"><button aria-pressed="true">リスト</button><button aria-pressed="false">グリッド</button></span>',
  '一覧のリスト表示とグリッド表示の切り替え。2つの文言と選択中の1つを渡します。',
  '選択中だけ `accent` で塗ります。'),
 ('TypeFilter',
  'Controls',
  160,
  '<button class="iconbtn typesbtn filtered">種別 <span class="count">2/3</span></button><div class="types" style="position:static;width:max-content;margin-top:4px"><label><input '
  'type="checkbox" checked> 開始</label><label><input type="checkbox" checked> 報告</label><label><input type="checkbox"> 質問</label></div>',
  'イベント種別の絞り込み。ボタンを押すとポップオーバーが開きます。種別名と選択状態を渡します。',
  '複数を同時に選べます。隠している種別があるときは、ボタンに `filtered` を付けて色を変えます。件数は「表示数/総数」で常に示します。'),
 ('EventRow',
  'Timeline',
  110,
  '<div class="ev"><time>06:40</time><span class="mark" style="background:var(--s-review)"></span><div class="body"><div class="head"><span '
  'class="who">ログ出力の構造化</span><span class="type">準備完了</span></div><div class="text">CI 緑、自己レビュー済み</div><div class="changes"><span class="chip">タスク '
  '1/2 → 2/2</span></div></div></div>',
  'タイムラインの1件。時刻、状態の色、セッション名、種別、本文を渡します。',
  '変化はチップで示します。'),
 ('KnowledgeCard',
  'Knowledge',
  120,
  '<div class="kcard" style="--kc:var(--s-needs)"><div class="ktitle">レート制限はスライディングウィンドウ方式にする</div><div class="kbody">固定ウィンドウでは境界で倍の要求が通る。</div><div '
  'class="kmeta"><span class="chip">redis</span></div></div>',
  '蓄積した知見のカード。題、本文、タグを渡します。左端の色は種類を示します。',
  '廃止した知見は `obsolete` で薄くします。'),
 ('DataTable',
  'Knowledge',
  120,
  '<div class="ctable-wrap"><table class="ctable"><tr><th>タイトル</th><th>報告元</th></tr><tr><td>lockfile は CI '
  'で固定する</td><td>依存パッケージ更新</td></tr></table></div>',
  'コレクションの表表示。列名と行を渡します。',
  '狭い幅では表だけを横スクロールさせます。')]

TYPE_STYLES = [('app-title', '16px', 700, 'ヘッダーの製品名。画面に1つだけ。', 'Session Hub'),
 ('panel-title', '13px', 700, 'パネルの見出し。', 'セッション'),
 ('body', '14px', 400, '既定の本文。セッション名は 600 にする。', '認証APIのレート制限'),
 ('body-sm', '13px', 400, '要約、質問、イベント本文。', '差分更新のテストを追加中'),
 ('group-heading', '12px', 600, 'セッション一覧のグループ見出し。', '要対応'),
 ('meta', '12px', 400, 'メタ情報、時刻、ボタン、タブ。', '#128 1/4 残≈7'),
 ('label', '11px', 600, '状態バッジ、日付の区切り、表の見出し。チップは 400。', '人間待ち')]

# {contrast} lists the fills on which white text falls below 4.5:1
README = """## 原則

Session Hub のダッシュボードは、並行する多数のセッションから「次に手を出すべきもの」を見つける画面です。密度を保ち、色は意味のあるところだけに使います。

- 色だけで状態を伝えない。必ず文言を添える。
- 強い塗りは状態バッジとグループ見出しのほか、選択中の切り替えに限る。本文やカードの地は塗らない。
- 影は使わない。面は `line` の罫線で分ける。例外は受信時のグローと、グリッドの詳細パネルの `shade` だけ。
- 対応が要るセッションは `s-needs` の枠で囲み、一覧の先頭に置く。

## 文字

`app-title`（16px）、`body`（14px）、`body-sm` と `panel-title`（13px）、`meta` と `group-heading`（12px）、`label`（11px）の5つのサイズだけを使います。新しいサイズを足しません。

グループ見出しは `group-heading`（12px）です。見出し全体が開閉ボタンで、状態の見出しだけラベルを `g-*` で塗ります。プロジェクトの見出しは塗りません。件数は右端に置きます。配下のセッション名（14px）より大きくせず、塗りで区切りを示します。状態バッジは `label` です。数字が並ぶ所は等幅数字にします。

## 色

本文は `ink`、補助文字は `muted` を、`bg`・`panel`・`hover` の上で使います。状態は `s-*`、グループ見出しは `g-*` です。`g-*` は両テーマ共通で、白文字を載せます。

次の塗りは、白文字とのコントラストが 4.5 に届かないテーマがあります。現行コードの値をそのまま記録しています：{contrast}。

## 余白と角丸

余白は `space-1` から `space-24` までの段階だけを使います。カードは上下 `space-10`、左右 `space-14`。枠の内側の角丸は、外側の角丸から枠線の1pxを引きます。角丸は部品の大きさに合わせ、チップ `radius-sm`、ボタン `radius-md`、パネル `radius-xl`、状態バッジ `radius-pill` を使います。

## 動き

受信時のグローは新しい状態の色で約6秒、3回明滅します。グリッドの詳細パネルは0.2秒で横から出ます。`prefers-reduced-motion` では静止した枠にします。

## 言葉

短い体言で書きます（「要対応」「作業中・待機」「レビュー可」）。ラベルは日本語と英語の両方を用意します（"Needs action"、"Working and waiting"）。絵文字は使いません。

## アイコンとロゴ

アイコンセットとロゴはありません。製品名は文字で組みます。印は丸いドットとスピナーだけです。
"""

COVER = """<!-- @dsCard height=288 -->
<!doctype html><html><head><style>
.cv{position:relative;width:960px;height:288px;background:var(--panel);overflow:hidden}
.cv svg{position:absolute;inset:0}.p{fill:var(--panel)}
.a{fill:var(--s-needs)}.b{fill:var(--s-work)}.c{fill:var(--s-review)}.d{fill:var(--ink)}.r{rx:var(--radius-xl)}
.tx{position:absolute;left:32px;bottom:24px;width:440px}
.nm{font:700 88px/.95 var(--font-sans);color:var(--ink)}.tg{font:400 14px/1.5 var(--font-sans);color:var(--muted);margin-top:10px}
</style></head><body><div class="cv"><svg width="960" height="288" viewBox="0 0 960 288">
<!-- blocks: s-needs 440x64, s-work 330x56, s-review 380x56, ink 300x40
arrangement: staggered swimlanes bleeding off the right edge
pattern: literal motif, event dots on lanes: each session is a band and each message a dot
scales: radius-xl corners, space-16 gaps -->
<rect class="a r" x="520" y="16" width="460" height="64"/><rect class="b r" x="568" y="92" width="412" height="56"/><rect class="c r" x="504" y="164" width="476" height="56"/><rect class="d r" x="696" y="236" width="284" height="40"/><circle class="p" cx="560" cy="48" r="8"/><circle class="p" cx="640" cy="48" r="8"/><circle class="p" cx="760" cy="48" r="8"/><circle class="p" cx="600" cy="120" r="8"/><circle class="p" cx="720" cy="120" r="8"/><circle class="p" cx="540" cy="192" r="8"/><circle class="p" cx="660" cy="192" r="8"/><circle class="p" cx="820" cy="192" r="8"/><circle class="p" cx="740" cy="256" r="8"/><circle class="p" cx="860" cy="256" r="8"/></svg>
<div class="tx"><div class="nm">Session Hub</div><div class="tg">次に手を出すべきセッションを見つける画面のために。</div></div></div></body></html>
"""
