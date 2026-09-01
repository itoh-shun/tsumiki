---
# ─────────────────────────────────────────────
# rig プロジェクト manifest — tsumiki
# ─────────────────────────────────────────────

# ── ビルド / Lint / テスト コマンド ──────────────────────
# root にビルド系ファイルは無い。Python サービスは service/ 配下（uv + hatchling）。
# Windows 側 Tauri アプリ（app/）を足したら build を埋めること。
build: ""
lint: ""
test: "cd service && uv run pytest"

# ── ブランチ & CI 戦略 ────────────────────────────────────
branch:
  base: "master"
  naming: ""
  ci: ""

# ── レビュアー ────────────────────────────────────────────
reviewer: "none"

# ── 本番影響変更 検知パターン ─────────────────────────────
# 単一 SQLite が正本で、書き込み口は REST サービスだけ。
# スキーマ・ストア・HTTP 表層・状態遷移表に触る変更は必ず review を通す。
production_impact:
  paths:
    - "service/app/db.py"
    - "service/app/store.py"
    - "service/app/main.py"
    - "service/app/models.py"
    - "service/app/backup.py"
  keywords:
    - "CREATE TABLE"
    - "PRAGMA"
    - "ALLOWED_TRANSITIONS"
    - "add_middleware"
    - "TrustedHost"
    - "completed_at"

# ── 使用 skill 列挙 ───────────────────────────────────────
skills: []

# ── Knowledge ソースポインタ ──────────────────────────────
knowledge:
  context_file: ""
  adr_dir: ""
  design_docs:
    - "DESIGN.md"

# ── デフォルト recipe ─────────────────────────────────────
default_recipe: "interactive"

# ── デフォルト persona ────────────────────────────────────
default_personas: []

# ── サイズ判定 閾値 ───────────────────────────────────────
size_thresholds:
  S_max: 100
  M_max: 200
  L_max: 400

# ── acceptance-gate 既定 K ────────────────────────────────
default_max_retries: 2

# ── デフォルト実行バックエンド ────────────────────────────
default_backend: manual

# ── 計算的オーケストレーション ────────────────────────────
default_orchestrate: false

# ── worktree 運用 ─────────────────────────────────────────
worktree:
  enabled: false
  root: ""
---

# tsumiki — rig manifest

ローカル完結型のタスク管理ツール。Windows 常駐 UI（Tauri）＋ WSL2 側 REST サービス（FastAPI + SQLite）。

## このプロジェクト固有の前提

- **書き込み口はひとつ。** 常駐 REST サービスだけが SQLite を書く。CLI と MCP は HTTP 経由の薄いクライアントで、ローカル DB へ直接触ってはいけない。
- **GTD の状態は5つ**（inbox / next / waiting / someday / done）。遷移の許可表は `service/app/models.py` が唯一の定義。`done` から `waiting` / `someday` には戻せない。
- **`completed_at` が非 NULL であることと `state == done` であることは常に一致する。**
- **利用者に見える文言は日本語。** 状態名の正典は 受信 / 次の行動 / 待ち / いつか / 完了（`service/app/state_labels.py`）。英語の state 値を日本語メッセージに混ぜない。
- **UI のデザインシステムは `DESIGN.md` が正本**（Notion を土台にした独自版）。色・タイポ・角丸はそこから引く。

## テスト

```
cd service && uv run pytest
bash scripts/smoke.sh                 # WSL2 側の end-to-end（専用ポート）
cd service && uv run python scripts/mcp_smoke.py   # MCP の stdio スモーク
```
