# Life Reroll API

FastAPI、SQLite 權威遊戲引擎、講師授課、背景教材／AI、教練與風險分析。

完整安裝、設定與啟動見 [根目錄 README](../README.md)，模組與測試範圍見 [開發說明](../docs/DEVELOPMENT.md)。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m app.main --host 127.0.0.1 --port 8000
.venv/bin/python -m pytest tests -q
```

預設 DB 為本目錄的 `game.sqlite3`，可用 `LIFE_REPLAY_DB` 覆寫；根目錄訓練啟動器使用 `training-local.sqlite3`。首次啟動建立新 DB，不附玩家資料或帳號。

`ai-config.example.json`、`mail-config.example.json` 是可提交範本；實際設定與 SQLite／WAL／SHM 均由 `.gitignore` 排除。

API 文件：`/docx`；機器契約：`/openapi.json`。教練、分析與訓練路由另見對應 `*_routes.py`。
