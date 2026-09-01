# tsumiki

Windows 常駐を想定したローカル完結型のタスク管理ツール。外部サービス連携なし。

- `DESIGN.md` — デザインシステム仕様書
- `service/` — Python サービス層（FastAPI + uv + hatchling + pytest）

## 開発

```bash
cd service
uv sync --extra dev
uv run pytest
```
