# tsumiki — 現状 (2026-09-01)

ローカル完結型のタスク管理ツール。**WSL2 側は完成、GUI は雛形まで。**

- リポジトリ: https://github.com/itoh-shun/tsumiki （PUBLIC / MIT）
- 設計の正本: `DESIGN.md`（UI）/ `CLAUDE.md`（守るべき約束）/ `.claude/rig.md`（rig manifest）

## 進捗

| | 状態 |
|---|---|
| T1〜T11（WSL2 側） | ✅ 完了・レビュー済み。126 tests passed |
| T12（Tauri 雛形） | ✅ 完了。`cargo check` / `cargo test`(2 passed) / `pnpm install` / `pnpm build` すべて成功 |
| T13（サービス起動管理） | ✅ 完了 |
| T14（トレイ常駐） | ⬜ 未着手 |
| T15（ホットキー入力欄） | ⬜ 未着手 |
| T16（入力欄→REST 配線） | ⬜ 未着手 |

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

## 次の一手

`C:\dev\tsumiki\app` で T14〜T16（トレイ常駐 → ホットキー入力欄 → REST 配線）。
`DESIGN.md` の「捕捉小窓」「積層バー」「タスク行」の節が実装仕様。

未確認の残件:
- `cargo check` の NTFS 上での所要時間（UNC では `cargo test` 実時間 15m39s）
- グローバルショートカットのハンドラは押下と解放の両方で発火するので、`state` が `Pressed` のときだけトグルすること
