# 開發與接續說明

## 系統分工

- `backend/app/main.py`、`handlers.py`、`store.py`：FastAPI、原版操作與 SQLite 交易。91 個已登錄操作的契約位於 `backend/data/api_registry.json` 與 `schema_reference.json`，訓練與教練另有路由。
- `engine.py`／`finance.py`：原版人生、資產、事件、金融 quote 與確認。quote 先在副本試算，確認才寫入。
- `training_catalog.py`／`training_engine.py`／`training_service.py`：獨立課程、來源、20 檔股票、固定班次路徑、學員進度與成效。發布後不能原地修改。
- `training_routes.py`／`training_jobs.py`／`training_materials.py`：講師權限、教材背景解析、AI 工作及契約檢查。
- `errors.py`：中文訊息、HTTP 狀態與附帶欄位／情境細節的 `UserError`。新增錯誤要同時檢查實際觸發條件與顯示內容。
- `qwen.py`／`zh.py`：Workspace NDJSON、主機備援、取消／封存與臺灣繁體。
- `radar.py`／`insights.py`／`scenarios.py`：當下風險、合成分岔預演。不得洩漏原存檔未來事件、種子或隱藏人物資料。
- 前端 `components/training/`：四步工作室、12 步導覽、學員遊玩。導覽使用記憶體範本，不替使用者上傳、產生或發布。
- 前端 `lib/game-client.ts`：具體錯誤、Bearer／CSRF、request key、讀寫連線差異與 PDF 下載。
- 前端 `lib/training-validation.ts`：每則 1–8 項引用、欄位範圍與出錯位置。不得默默刪掉超限或失效引用。
- `scripts/training-tailscale.py`：只讀取已連線的 Tailscale IPv4 並啟動私有網站代理。

## 資料與權限

`game.sqlite3` 與 `training-local.sqlite3` 都是執行時資料，不屬於程式版本。實際使用哪個由 `LIFE_REPLAY_DB` 決定；不要只憑網址猜 DB。訓練資料位於 `training_*` 表。

寫入使用交易、版本與 Idempotency-Key。結果不確定時沿用原請求重試，不能換新 key 猜測重送。講師教材／教案／班次依擁有者隔離，學員只讀本人進度，作答前不回傳正確答案。

手機和電腦共用後端已儲存內容，各自登入；未儲存的 React 草稿不會自動同步。不要為了測試重新整理使用者的未儲存編輯。不同 port 仍可能共用同一 host 的 cookie，隔離 QA 應使用不同 host／profile 與合成帳號。

## 已驗收範圍（2026-10-30）

- 146 項後端回歸、24 項客戶端錯誤／私有 HTTP 檢查、93 項客戶端整合檢查與三輪人生通過；隨機事件可能讓整合檢查數不同。
- TypeScript typecheck、Vite build、Chrome 桌面／390px／320px。
- iPhone Safari 經 4G + Tailscale：講師登入、略過導覽、教案／班次切換、重整後維持登入。不是完整學員結課或所有檔案格式的真機驗收。
- 模型備援曾真實完成六則編課並走過審核／發布／開班；正常自動測試不依賴該私有模型服務。
- 本機玩家與訓練資料曾逐表比較完整資料列與 SQLite integrity／FK；證據保留於原機器，未上傳包含教材或帳號的原始 QA。

原始測試資料、畫面截圖、模型回覆、私有帳號與完整本機交接不納入此儲存庫。不要以某次舊 snapshot 覆蓋使用者後續新增內容。

## 修改與驗證

先讀根目錄 README 和相關模組。依改動執行有意義的後端回歸／客戶端測試、typecheck／build 與必要的瀏覽器驗收。使用暫存 DB、停用真實模型及外寄郵件，除非該次任務明確需要真實服務。

版本庫不含 dist；可用 `git archive HEAD` 建立純來源副本，再從該副本建置，以檢查是否依賴被忽略的本機檔案。來源圖片放 `source-assets/`，可公開服務的最佳化版本放 `public/`，部署完整 build 的 `dist/`。

## 已知限制

沒有 OCR；掃描教材需先取得可讀文字。AI 語意與正式保單仍須講師核對，來源節錄不等於全文審查。教學保費、股價、年金與理賠數值是模擬假設，沒有真實精算或核保。尚未驗證正式主機的實際高併發容量。
