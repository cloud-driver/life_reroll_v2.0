# Life Reroll 前端

React 19、TypeScript 與 Vite。保留原整合時的目錄名稱，以維持啟動及測試路徑相容。

```sh
npm ci
npm run typecheck
npm run build
python3 serve.py --host 127.0.0.1 --port 5173 --api-proxy http://127.0.0.1:8000
```

需要 Node.js 22.13+。儲存庫不含 `node_modules` 或 `dist`；從 GitHub 下載後先建置。開啟 `http://127.0.0.1:5173/full` 或 `/teach`、`/training`。

`public/config.js` 預設留空 API base，走網站同來源代理。`public/` 包含執行時圖片；`source-assets/` 保留原始素材，不會由 `serve.py` 直接公開服務。部署使用完整 build 產生的 `dist/`。

本機訓練、手機入口與設定詳見 [根目錄 README](../README.md)；開發位置與驗收範圍見 [開發說明](../docs/DEVELOPMENT.md)。
