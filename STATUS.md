# tsumiki — 現状 (2026-09-03)

ローカル完結型のタスク管理ツール。**v0.1 の GUI まで完成。**
トレイに常駐し、`Alt+Shift+Space` で出る小窓から inbox にタスクを積める。
実機での目視確認まで完了（下記）。一覧 UI は未着手。

- リポジトリ: https://github.com/itoh-shun/tsumiki （PUBLIC / MIT）
- 設計の正本: `DESIGN.md`（UI）/ `CLAUDE.md`（守るべき約束）/ `.claude/rig.md`（rig manifest）

## 進捗

| | 状態 |
|---|---|
| T1〜T11（WSL2 側） | ✅ 完了・レビュー済み。126 tests passed |
| T12（Tauri 雛形） | ✅ 完了。`cargo check` / `cargo test`(2 passed) / `pnpm install` / `pnpm build` すべて成功 |
| T13（サービス起動管理） | ✅ 完了 |
| T14（トレイ常駐） | ✅ 完了。実機確認済み |
| T15（ホットキー捕捉小窓） | ✅ 完了。実機確認済み |
| T16（入力欄→REST 配線） | ✅ 完了。実機確認済み |
| T17（一覧ウィンドウ） | ✅ 完了。状態チップ・タスク行・フッタ。読み取りのみ |
| T18（行の操作） | ✅ 完了。実機確認済み |

## 作業場所が2つに分かれている（重要）

| 場所 | 役割 |
|---|---|
| `/home/itoshun/works/tsumiki`（WSL2） | **`service/` の正本。** サービスもここで動く |
| `C:\dev\tsumiki`（Windows・NTFS） | **`app/` の正本。Tauri のビルドはここでしか通らない** |

同期は GitHub 経由。`app/` と `service/` に依存関係は無いので衝突はほぼ起きない。
WSL2 からは `/mnt/c/dev/tsumiki` で読み書きできるが、**ビルドは必ず Windows 側のネイティブパス**で行う。

理由は `app/README.md` に記録（WSL の UNC パス上では Rust も pnpm もネイティブな
低レベル FS 操作が通らず、3種類の異なる壊れ方をした）。

## 起動

```bash
# サービス（WSL2）
cd /home/itoshun/works/tsumiki/service && uv run tsumiki-service    # 127.0.0.1:7331
curl -s http://127.0.0.1:7331/health

# CLI（WSL2・別ターミナル）
cd /home/itoshun/works/tsumiki/service && uv run tsumiki ls

# テスト
cd /home/itoshun/works/tsumiki/service && uv run pytest             # 126 passed
bash /home/itoshun/works/tsumiki/scripts/smoke.sh                   # end-to-end
cd /home/itoshun/works/tsumiki/service && uv run python scripts/mcp_smoke.py
```

MCP は user スコープで登録済み（`uv --directory /home/itoshun/works/tsumiki/service run tsumiki-mcp`）。
データは `~/.tsumiki/`（DB / backups / logs、いずれも 0600）。

## 設計上の確定事項

- **書き込み口はひとつ。** 常駐 REST サービスだけが SQLite を書く。CLI と MCP は HTTP 越しの薄いクライアント。サービス停止中は明示エラーで止める
- **GTD の5状態**（受信 / 次の行動 / 待ち / いつか / 完了）。遷移の許可表は `service/app/models.py` が唯一の定義。`done` から `waiting` / `someday` には戻せず、同一状態への遷移も不許可
- **`completed_at` が非 NULL ⇔ `state == done`**（状態由来の不変条件）
- **利用者に見える文言は日本語。** 状態名の正典は `service/app/state_labels.py`
- **UI は `DESIGN.md`（Notion 土台の独自版）が正本。** 琥珀のアクセントと積層バーが tsumiki 固有
- 外部連携なし・認証なし（本人専用のローカルツール）。ただし DNS rebinding 対策として Host 検証あり
- ローカル化の目的は**一元管理と所有**であって機密遮断ではない。タスク本文が MCP 経由で Claude に渡ることは許容済み

## 独立レビューで塞いだもの（再発させないこと）

1. `completed_at` の書き込み口が二重化し、CLI の `mv <id> 完了` で完了時刻が入らなかった
2. Host 検証が無く、DNS rebinding でタスクの窃取・全削除ができた
3. `smoke.sh` が `TSUMIKI_PORT` を export せず、本番 DB に書き込みうる経路があった
4. 404 / 422 の body がテストで固定されておらず、メッセージを書き換えても全テストが通った

## 実機で確認したこと（2026-09-03・一覧ウィンドウ）

5状態に1件ずつ置いた本番データで、人間の目で確認した。**すべて通っている。**

| | |
|---|---|
| 一覧のカードが `#f6f5f4` の地から浮いて見える | ✅ |
| 5行が状態ごとに違って見える（左の色バー・完了だけ取り消し線と緑チェック） | ✅ |
| **完了の行のメニューが「受信へ」「次の行動へ」の2つだけ**（他は4つ） | ✅ |
| 削除が2段階（一度で消えない） | ✅ |

3つ目が肝。`models.py` の `ALLOWED_TRANSITIONS` が `GET /meta/transitions` 経由で
メニューに効いていることの確認になる。フロントに表の写しはない。

## 実機で確認したこと（2026-09-02・トレイと捕捉小窓）

`pnpm tauri dev` を本番構成・本番データ（`~/.tsumiki/`）で起動し、人間の目で7項目を確認した。
**すべて通っている。**

| | |
|---|---|
| トレイにアイコンが出る（既定では「隠れているアイコン」の中） | ✅ |
| 右クリックで 表示 / 一時停止 / 終了 が日本語で出る | ✅ |
| ウィンドウの ✕ でアプリが終了せず、トレイに残る | ✅ |
| `Alt+Shift+Space` で小窓が出る（1回の押下で） | ✅ |
| 小窓の四辺に Deep Shadow が出て、他アプリの上に浮いて見える | ✅ |
| 積層バーが inbox の件数どおりに積まれる | ✅ |
| **サービス停止中に Enter を押すと、閉じずに日本語エラーが出る** | ✅ |

最後の1つは「サービス停止中は黙って捨てず明示エラーで止める」という約束そのもの。
アプリが `ensure_running()` で WSL2 側のサービスを自分で起動することも実機で確認した。

## 実装で踏んだ落とし穴（再発させないこと）

- **`box-shadow` はウィンドウ矩形の外に描けない。** カードをウィンドウ全域に広げると
  Deep Shadow が全周で切れて消える。ウィンドウ 840×216 に対しカード 720×96 を中央に置く
- **グローバルショートカットは押下と解放の両方で発火する。** `Pressed` だけを見ないと、
  押した瞬間に開いて離した瞬間に閉じる
- **フォーカス喪失で閉じる処理には状態のガードが要る。** 時間で待つ（n ms 以内は無視）と
  マシン速度に依存する。一度 `Focused(true)` を観測してからでないと閉じないようにした
- **`Ctrl+Shift+Space` / `Ctrl+Alt+Space` / `Win+Shift+Space` は実機で埋まっていた。**
  常駐アプリ（Intel Graphics Software のオーバーレイが有力）が取っている
- **このマシンは DPI 150%。`PrintWindow` のスクリーンショットは信用できない。**
  WebView2（Chromium）のコンテンツを正しく捉えず、実際には収まっているレイアウトが
  崩れて見える。一覧ウィンドウの幅を 720 → 1180px まで広げる誤対応をここで踏んだ
  （実測では 720px に 166px の余裕があった）。**見た目の検証はスクリーンショットではなく
  `getBoundingClientRect()` の実測か、人間の目で行う**
- **`Inter` と `JetBrains Mono` はこのマシンに入っていない。** 欧文は `Segoe UI`、
  等幅は `monospace` のフォールバックで描画されている（和文の `Noto Sans JP` は入っている）。
  `DESIGN.md` が想定した見た目と実機の見た目には差がある
- **Windows 側と WSL2 側で同じリポジトリを触ると改行が壊れる。** `.gitattributes` で
  LF に固定して構造的に防いだ。`/mnt/c` 配下で `git add`/`commit` はしない

## 常用のしかた

リリースビルドは `C:\dev\tsumiki\app` で `pnpm tauri build`。成果物:

```
src-tauri/target/release/bundle/msi/tsumiki_0.1.0_x64_en-US.msi    5.3 MB
src-tauri/target/release/bundle/nsis/tsumiki_0.1.0_x64-setup.exe   3.8 MB
src-tauri/target/release/app.exe                                  15.8 MB
```

**ログは `%LOCALAPPDATA%\dev.itoshun.tsumiki\logs\tsumiki.YYYY-MM-DD.log`。**
日次ローテーション・14日保持。既定は `info`、`RUST_LOG` で上書きできる。
リリースビルドはコンソールを持たないので、**障害を追う手段はこのファイルだけ**。

## 分かっていて直していないこと

直す価値が出るまで手を付けない、と決めたもの。**バグではなく、判断の記録。**

- **`service_mgr.rs` の `service_cmd` は絶対パスのハードコード**
  （`uv --directory /home/itoshun/works/tsumiki/service run tsumiki-service`）。
  実行ファイルからの相対ではないので、リポジトリを別の場所に置くと動かない。
  `TSUMIKI_SERVICE_CMD` で上書きできることは実測済み。
  **今直さない理由**: 直すには「実行ファイルからの相対」か「設定ファイル」かの設計判断が要り、
  それは配布を考える段になって初めて意味を持つ。今の目的は自分のマシンで常用すること
- **リリースビルドでは WebView2 の devtools が無効**（`devtools` フィーチャ未指定）。
  配布物で開発者ツールが開ける方が望ましくないので、**そのままにする**

## 次の一手

**一覧ウィンドウ**（`DESIGN.md` の「一覧ウィンドウ」「タスク行」）。メインウィンドウは今
`<div>tsumiki</div>` のプレースホルダー。状態チップ・タスク行・積層バーのミニ版を作る。

その他の残件:
- トレイアイコンが Tauri の既定のまま。tsumiki 固有のものにする
- 一時停止の状態がトレイのチェックだけで、小窓側に見えない
- systemd 自動起動と `uv tool install`（ユーザー判断で保留中）
