# tsumiki Design System

> Inspired by [Notion](https://notion.so). 土台は `VoltAgent/awesome-design-md` の Notion DESIGN.md（MIT）。
> 商標・ブランド資産は Notion Labs, Inc. に帰属する。本書は tsumiki 固有の設計判断を上乗せしたもので、
> Notion のブランド色（Notion Blue）・ロゴ・専用書体（NotionInter）は使用しない（§8 の逸脱表を参照）。

tsumiki は Windows に常駐するローカル完結型のタスク管理ツール。捕捉（inbox）が最速であることを
最優先し、処理と一望はその次に置く。**溜まったタスクを見て気が重くならないこと**を、常駐ツール
固有の要件として扱う。

---

## 1. Visual Theme & Atmosphere

冷たいグレーではなく**温かいニュートラル**で組む。灰色に黄土の下地を持たせると、画面が
「ガラス」ではなく「上質な紙」に近づく。tsumiki は一日中視界の端にいるので、そこが決定的に効く。

黒も純黒にしない。`rgba(0,0,0,0.95)` の近似黒は、気づかないレベルで読み心地を柔らかくする。

境界線は**ささやき**にする。`1px solid rgba(0,0,0,0.1)`。重い罫線でも影でもなく、
かろうじて見える分割線で構造を作る。影は不透明度 0.05 未満の層を4〜5枚重ね、
「見える影」ではなく「感じる奥行き」にする。

積み木のモチーフは、この温度のもとで初めて本来の意味を持つ。**積層バーのブロックは
角丸 4px の小さな板**で、実際に積み木として読める。

### Key Characteristics

- 温かいニュートラル: `#f6f5f4`（地）/ `#ffffff`（面）/ `#615d59`（副）/ `#a39e98`（淡）
- 近似黒 `rgba(0,0,0,0.95)`。純黒 `#000000` は使わない
- ささやきの境界 `1px solid rgba(0,0,0,0.1)`。これより重い線を引かない
- 多層の柔らかい影（個々の不透明度は 0.05 以下）
- 彩色はアクセントの琥珀と完了の緑だけ
- ウェイトは 400 / 500 / 600 / 700 の四段
- 数字を多く出すので `font-feature-settings: "lnum"` を全体にかける

---

## 2. Color Palette & Roles

### 面（Surfaces）

| 役割 | 値 | 用途 |
|---|---|---|
| Canvas | `#f6f5f4` | 最外背景。ウィンドウの地 |
| Surface | `#ffffff` | 一覧ウィンドウ、捕捉小窓、カード |
| Sunken | `#f6f5f4` | 面の中でへこませたい領域（積層バーの帯など） |
| Hover | `rgba(0,0,0,0.03)` | 押せる面のホバー |
| Selected | `rgba(0,0,0,0.05)` | 選択中の行 |

> Notion はページ地を白、交互のセクションを `#f6f5f4` にする。tsumiki は**逆**にして、
> 地を温かい白、カードを純白にした（§8）。常駐ウィンドウは「カードが浮いて見える」必要があるため。

### 文字（Text）

| 役割 | 値 | 用途 | 白地でのコントラスト |
|---|---|---|---|
| Primary | `rgba(0,0,0,0.95)` | タスクタイトル、入力中の文字 | 約 18:1 |
| Secondary | `#615d59` | メタ情報、説明、キーバインド表示 | 約 5.5:1 |
| Muted | `#a39e98` | **プレースホルダと装飾のみ** | 約 2.6:1 — AA 未達 |

**読ませる必要のあるテキストの下限は Secondary `#615d59`。** `#a39e98` を本文・メタ・ラベルに
使わない（§8 の逸脱表を参照）。

### アクセント（Accent）

| 役割 | 値 | 用途 | 備考 |
|---|---|---|---|
| Accent | `#a8620f` | 文字・リンク・主ボタンの背景 | 白地で 約 4.8:1 |
| Accent Strong | `#8a4f0a` | ホバー・押下 | |
| Accent Fill | `#d98324` | **塗り面専用**（積層バー、状態バー） | 文字色には使わない |
| Accent Tint | `#fdf3e8` | バッジ・チップの背景 | |
| On Accent | `#ffffff` | `#a8620f` の上に載る文字 | |

`#d98324` は明るすぎて文字には使えない。**塗りは `#d98324`、文字は `#a8620f`** と使い分ける。

### 状態（GTD States）

| 状態 | 値 | 備考 |
|---|---|---|
| 受信 (inbox) | `#d98324` | 唯一「目を引いてよい」状態 |
| 次の行動 (next) | `#31302e` | 温かい濃色 |
| 待ち (waiting) | `#615d59` | |
| いつか (someday) | `#a39e98` | 状態バーは装飾なので Muted で可 |
| 完了 (done) | `#1aae39` | **アイコンにのみ**。ストロークは 2px 以上（細いと白地で沈む） |

### 境界と影

| 役割 | 値 |
|---|---|
| Whisper Border | `1px solid rgba(0,0,0,0.1)` |
| Divider | `1px solid rgba(0,0,0,0.06)`（行の区切り。ささやきよりさらに軽く） |
| Soft Card Shadow | `rgba(0,0,0,0.04) 0px 4px 18px, rgba(0,0,0,0.027) 0px 2.025px 7.84688px, rgba(0,0,0,0.02) 0px 0.8px 2.925px, rgba(0,0,0,0.01) 0px 0.175px 1.04062px` |
| Deep Shadow | `rgba(0,0,0,0.01) 0px 1px 3px, rgba(0,0,0,0.02) 0px 3px 7px, rgba(0,0,0,0.02) 0px 7px 15px, rgba(0,0,0,0.04) 0px 14px 28px, rgba(0,0,0,0.05) 0px 23px 52px` |

---

## 3. Typography

### フォント

| 用途 | スタック |
|---|---|
| 欧文 | `Inter`, `-apple-system`, `system-ui`, `Segoe UI`, `Helvetica`, `Arial` |
| 和文 | `Noto Sans JP`, `Hiragino Sans`, `Yu Gothic UI`, `Meiryo` |
| 等幅 | `JetBrains Mono`, `ui-monospace`, `SF Mono`, `Menlo` |

- 実際の指定は `font-family: "Inter", "Noto Sans JP", ...` の順。欧文と和文が自動で振り分けられる。
- **全体に `font-feature-settings: "lnum"`** をかける（件数・時刻・ポート番号が揃う）。
- 等幅は**技術的な文字列にだけ**使う（キーバインド、ポート番号）。日時や件数には使わない
  — 等幅は硬い印象を与えるので、フレンドリーな地には最小限にとどめる。

### スケール

| 役割 | サイズ | ウェイト | 行高 | トラッキング | 用途 |
|---|---|---|---|---|---|
| Capture Input | 20px | 500 | 1.40 | -0.125px | 捕捉小窓の入力文字 |
| Panel Title | 16px | 700 | 1.30 | -0.25px | ウィンドウ名 |
| Section Label | 14px | 600 | 1.43 | normal | セクション見出し |
| Row Title | 15px | 400 | 1.47 | normal | タスクのタイトル |
| Body | 14px | 400 | 1.50 | normal | 説明文 |
| Chip / Button | 13px | 600 | 1.33 | normal | チップ、ボタン、メニュー |
| Meta | 13px | 400 | 1.43 | normal | 日時・状態 |
| Badge | 12px | 600 | 1.33 | 0.125px | バッジ（**正のトラッキング**） |

### 原則

- **四段のウェイト。** 400 は読む、500 は触る、600 は強調、700 は宣言。
- **12px のバッジだけ正のトラッキング**（`0.125px`）。小さい文字を開いて読みやすくする。
  これはシステム内で唯一の正のトラッキング。
- **和文に強い負トラッキングをかけない。** 最大でも `-0.02em`
  （Notion の `-2.125px @64px` 級は欧文の表示サイズ専用。tsumiki に表示サイズは存在しない）。
- 本文は 14px を下限にする。常駐 UI でも、読ませる文字を 13px 未満にしない
  （13px はチップとメタまで）。

---

## 4. Component Stylings

### Notion 由来

**Primary Button** — bg `#a8620f` / text `#ffffff` / padding 8px 16px / radius 4px / hover bg `#8a4f0a`

**Secondary Button** — bg `rgba(0,0,0,0.05)` / text `rgba(0,0,0,0.95)` / padding 8px 16px / radius 4px

**Ghost Button** — bg transparent / text `rgba(0,0,0,0.95)` / ホバーで下線

**Pill Badge** — bg `#fdf3e8` / text `#a8620f` / padding 4px 8px / radius 9999px / 12px 600 / tracking 0.125px

**Card** — bg `#ffffff` / border Whisper / radius 12px / Soft Card Shadow

**Input** — bg `#ffffff` / border `1px solid #dddddd` / radius 4px / placeholder `#a39e98`

**Focus** — `2px solid #a8620f` の outline（すべての操作可能な要素に必ず付ける）

### tsumiki 固有

#### 捕捉小窓（Capture Window）

呼び出し: `Ctrl + Shift + Space`。他のアプリの上に出る。

- 幅 720px 固定、高さは内容依存（最小 96px）
- bg `#ffffff` / border Whisper / radius 16px / **Deep Shadow**
- 左端に積層バー（下記）、右端に `Enter` ラベル（13px `#615d59`）と矢印アイコン（`#a8620f`）
- 入力は Capture Input スケール。プレースホルダ `#a39e98`
- `Esc` で閉じる。**確認ダイアログを挟まない**（捕捉の速さが最優先）

#### 積層バー（Stack Bar）

**tsumiki の唯一のモチーフ。** 受信に何件積まれているかを、下から積み上げた板の厚みで示す。

- ブロック 24×8px / **radius 4px** / gap 3px / 下揃え
- 最上段のみ `#d98324`、以下は `#e8e4e0` → `#f0ece8` へ淡くしていく
- 帯の地は `#f6f5f4`（Sunken）。白い面の中でわずかにへこませる
- 最大 8 段。超えたら最上段の上に `+n` を 12px 600 `#615d59` で置く
- 0 件のときはブロックを描かず、帯の領域だけ残す（レイアウトが動かないように）
- **積み木の比喩をここ以外に持ち込まない。** カードをブロック状に並べたり、
  角丸を過剰にしたりしない。

#### タスク行（Task Row）

- 最小高 56px / padding 14px 18px / gap 14px / flex
- 左端に状態バー 3px 幅・`align-self: stretch`・radius 4px（色は §2 の状態表）
- 状態アイコン 18px の円（stroke `#a39e98` / 1.6px）。完了のみチェック入りで `#1aae39` / stroke 2px
- タイトルは Row Title。完了行は `#615d59` + `line-through`
- メタは Meta スケール `#615d59`。`2 分前 · 受信` の形式で中黒区切り
- 区切りは Divider。最終行には引かない
- hover `rgba(0,0,0,0.03)` / 選択 `rgba(0,0,0,0.05)`

#### 一覧ウィンドウ（List Window）

- bg `#ffffff` / border Whisper / radius 12px / Soft Card Shadow
- ヘッダ: 左に積層バーのミニ版（16×5px を2段）+ `tsumiki`（Panel Title）、右に状態チップの列
- フッタ: キーバインドと接続先。キーバインドは等幅 13px `#615d59`
- 行が尽きた下は `#ffffff` のまま。**白がそのまま余白**になる

---

## 5. Layout

- 基準単位 8px。実際に使う値: 3 / 4 / 6 / 8 / 12 / 14 / 16 / 18 / 24 / 32
- ウィンドウ内側の余白は 32px、パネル内側は 18px
- セクション間は 24px。**区切り線は引かない**（余白が分ける）

### Radius Scale

| 値 | 用途 |
|---|---|
| 4px | ボタン、入力欄、積層バーのブロック、状態バー |
| 8px | メニュー、ポップオーバー、小さなカード |
| 12px | 一覧ウィンドウ |
| 16px | 捕捉小窓（最も浮く面） |
| 9999px | 状態チップ、バッジ |

---

## 6. Depth & Elevation

| レベル | 扱い | 用途 |
|---|---|---|
| 0 | `#f6f5f4`、影なし | 最外背景 |
| 1 | border Whisper のみ | 区切り、インラインの枠 |
| 2 | `#ffffff` + Whisper + Soft Card Shadow | 一覧ウィンドウ、カード |
| 3 | `#ffffff` + Whisper + Deep Shadow | 捕捉小窓（他アプリの上に出る唯一の面） |

影は**層を重ねて作る**。単層の濃い影を使わない。個々の層の不透明度は 0.05 を超えない。

---

## 7. Do's and Don'ts

### Do

- 温かいニュートラルを使う（`#f6f5f4` / `#31302e` / `#615d59` / `#a39e98`）
- 一次テキストは `rgba(0,0,0,0.95)`
- 境界は `1px solid rgba(0,0,0,0.1)` のささやき
- 影は4〜5層を重ねる
- 塗りは `#d98324`、文字は `#a8620f` と使い分ける
- 12px のバッジにだけ正のトラッキング `0.125px`
- 全体に `font-feature-settings: "lnum"`
- 操作可能な要素すべてに `2px solid` の focus outline

### Don't

- **読ませるテキストに `#a39e98` を使わない**（AA 未達）
- **`#d98324` を文字色に使わない**（白地で約 2.9:1）
- 純黒 `#000000` を本文色にしない
- 青みのあるグレーを使わない（Notion の灰は黄土寄り）
- 重い境界線・単層の濃い影を使わない
- 状態に新しい色相を足さない（琥珀と完了の緑以外）
- **和文に強い負トラッキングをかけない**（最大 `-0.02em`）
- **積み木の比喩を積層バー以外に持ち込まない**
- 等幅を日時・件数に使わない（技術的な文字列だけ）
- 捕捉に確認ダイアログを挟まない
- 装飾でアクセントを塗らない

---

## 8. Notion からの意図的な逸脱

そのまま持ってこられなかった箇所と、その理由。**これは妥協の記録であって、直すべき差分ではない。**

| Notion | tsumiki | 理由 |
|---|---|---|
| NotionInter | Inter + Noto Sans JP | NotionInter は非公開。Notion 自身の fallback 先頭が Inter。加えて UI が日本語で、Inter に CJK グリフが無い |
| Notion Blue `#0075de` | Amber `#a8620f` / `#d98324` | ブランド固有色は流用しない。**「彩色はアクセント1色だけ」という規則は維持し、色相だけ差し替えた** |
| Muted `#a39e98` をキャプションに使用 | 読ませるテキストの下限は `#615d59` | `#a39e98` は白地で約 2.6:1。WCAG AA（4.5:1）に届かない |
| ページ地が白、交互セクションが `#f6f5f4` | 地が `#f6f5f4`、カードが白 | 常駐ウィンドウは「カードが浮いて見える」必要がある。マーケサイトの交互配色とは目的が違う |
| 表示サイズに強い負トラッキング（-2.125px @64px） | 和文は `-0.02em` まで。表示サイズ自体が存在しない | 日本語は字面が正方形で、詰めると可読性が落ちる。常駐 UI に見出しは要らない |
| 等幅の規定なし | JetBrains Mono を技術的文字列にのみ追加 | キーバインドとポート番号には等幅が要る。ただし用途を限定して硬さを抑える |
| セクション間 64–120px | セクション間 24px、行 56px | 常駐ツールは一望性が要る。スクロールさせない |
| イラスト・キャラクター | なし | 常駐ウィンドウに装飾を置く余地がない。温かさは配色と積層バーで出す |

---

## 9. Agent Prompt Guide

### クイックリファレンス

```
最外背景        #f6f5f4
面（カード）    #ffffff
一次テキスト    rgba(0,0,0,0.95)
二次テキスト    #615d59   ← 読ませるテキストの下限
装飾のみ        #a39e98
アクセント文字  #a8620f   （ホバー #8a4f0a）
アクセント塗り  #d98324
アクセント淡    #fdf3e8
完了            #1aae39   （アイコンのみ・stroke 2px）
境界            1px solid rgba(0,0,0,0.1)
行の区切り      1px solid rgba(0,0,0,0.06)
```

### 指示文の例

- 「タスク行を作れ。最小高 56px、padding 14px 18px、gap 14px の flex。左端に 3px 幅・radius 4px の
  状態バー（受信なら `#d98324`）、18px の円アイコン（stroke `#a39e98` 1.6px）、タイトルは 15px
  weight 400 `rgba(0,0,0,0.95)`、メタは 13px `#615d59` で `2 分前 · 受信`。区切りは
  `border-bottom: 1px solid rgba(0,0,0,0.06)`。ホバーは `rgba(0,0,0,0.03)`。」

- 「捕捉小窓を作れ。幅 720px、bg `#ffffff`、border `1px solid rgba(0,0,0,0.1)`、radius 16px、
  Deep Shadow（5層）。左に幅 48px の積層バー（地は `#f6f5f4`、24×8px・radius 4px のブロックを
  gap 3px で下揃え、最上段だけ `#d98324`）、入力は 20px weight 500 letter-spacing -0.125px、
  右に `Enter` を 13px `#615d59` で。」

- 「バッジを作れ。bg `#fdf3e8`、text `#a8620f`、radius 9999px、padding 4px 8px、12px weight 600、
  letter-spacing 0.125px。」

### 反復の指針

1. 灰色は必ず黄土寄り。青みのある灰を使ったらそれは間違い
2. ウェイトは 400 / 500 / 600 / 700 の四段
3. 境界はささやき、影は多層。単層の濃い影を使わない
4. 塗りは `#d98324`、文字は `#a8620f`
5. `#a39e98` を読ませるテキストに使ったら、それは間違い
6. 積み木の比喩は積層バーだけ

---

## 出典

- 土台: [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md)（MIT License）の Notion DESIGN.md
- Inspired by [Notion](https://notion.so)。商標・ブランド資産は Notion Labs, Inc. に帰属する
- フォント: [Inter](https://rsms.me/inter/)（SIL OFL）/ [Noto Sans JP](https://fonts.google.com/noto/specimen/Noto+Sans+JP)（SIL OFL）/ [JetBrains Mono](https://www.jetbrains.com/lp/mono/)（SIL OFL）

## 変更履歴

- 2026-09-01: 土台を Linear（暗色ネイティブ）から Notion（温かい明色）へ変更。
  「明るくフレンドリーに」という要件は配色の差し替えでは満たせず、設計思想ごと入れ替えたため。
  琥珀のアクセントと積層バーのモチーフは引き継いだ。
