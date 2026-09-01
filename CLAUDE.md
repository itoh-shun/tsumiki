# tsumiki

ローカル完結型のタスク管理ツール。Windows 常駐 UI（Tauri 2）＋ WSL2 側 REST サービス（FastAPI + SQLite）。
AI からは MCP / CLI / REST の3経路で操作する。外部 SaaS 連携なし。

## 守るべき約束

- **書き込み口はひとつ。** 常駐 REST サービスだけが SQLite を書く。CLI と MCP は HTTP 経由の薄いクライアントで、ローカル DB へ直接触ってはいけない。サービス停止中は明示エラーで止める（黙って別経路で書かない）。
- **GTD の状態は5つ**（inbox / next / waiting / someday / done）。遷移の許可表は `service/app/models.py` が唯一の定義。`done` から `waiting` / `someday` には戻せず、同一状態への遷移も不許可。
- **`completed_at` が非 NULL であることと `state == done` であることは常に一致する。**
- **利用者に見える文言は日本語。** 状態名の正典は 受信 / 次の行動 / 待ち / いつか / 完了（`service/app/state_labels.py`）。英語の state 値を日本語メッセージに混ぜない。
- **UI は `DESIGN.md` が正本。** Notion を土台にした独自のデザインシステム。色・タイポ・角丸・コンポーネントはそこから引く。勝手に新しい色相を足さない。

## よく使うコマンド

```
cd service && uv sync --extra dev          # 依存の同期
cd service && uv run pytest                # ユニットテスト
cd service && uv run tsumiki-service       # 常駐サービス（127.0.0.1:7331）
cd service && uv run tsumiki ls            # CLI
bash scripts/smoke.sh                      # WSL2 側の end-to-end
cd service && uv run python scripts/mcp_smoke.py   # MCP の stdio スモーク
```

## Compact Instructions

If a rig harness run is active when compacting, preserve in the summary:
- the rig run-status (recipe, current step + position, gate state, mode);
- the active recipe's remaining/done steps and the current step id;
- the acceptance contract in force (acceptance-gate criteria / goal-loop goal) and unresolved REJECT/conditions;
- the user's goal/intent, key decisions, and stuck-guard counters;
- the context-minimal discipline (real work is delegated to subagents; the parent only aggregates + gates).
After compaction, re-emit the rig run-status header and re-anchor to the current step before doing any work.
