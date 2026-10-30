# 前端交接 — v1.2 整合版

基準為組員提供的 2026-10-16 前端。完整啟動說明與已知驗證限制以根目錄 README.md、docs/DEVELOPMENT.md 為準。

## 責任與流程

前端呈現場景、移動、對話、交易確認單與報表；骰子、時間、事件、股價、保障資格、入帳及存檔都由 backend 決定。正式入口 /full，/demo 是獨立離線展示。

1. 註冊／登入，依 bootstrap.email_verification_required 決定是否需要驗證。開發模式由後端跳過驗證。
2. 建立人生，前往金融大樓配置，回家確認初始配置。
3. HOME_READY 在家擲骰；每個事件提供固定選項，前端不代選。
4. FUNDING 先核對事故當時保障、申請理賠，再決定出售資產、解定存、借款或付款；核准未入帳不能當作現金。
5. EVENT_RESULT 確認後繼續原骰子剩餘年數。等待期間經過的事件排隊處理。
6. TURN_REVIEW 檢視結算與快照，確認後依 daily_phase 進入工作或自由準備。
7. WORK_REQUIRED 只能前往工作區；WORKING 用 C08 complete_work:true 完成工作；RETURN_HOME 先返家，之後恢復 HOME_READY。工作動作不額外發薪。退休／待業沒有必須上班的階段。
8. ENDED 顯示本輪報告與重生準備點，三輪後可下載總評 PDF。保留事件及外部原因，決策效果可以改變。

## 介面

- lib/game-client.ts 統一處理 Cookie／Bearer、API 網址、錯誤、冪等與 PDF。預設網址由 public/config.js 提供。
- 所有寫入沿用 use-game.ts 的 game.write，帶 expected_version 及 Idempotency-Key。不要改 UI 餘額當作交易成功。
- lib/game-recovery.ts 以 API 來源及使用者區隔原請求，不保存密碼。斷線時沿用原鍵安全重試。
- lib/contracts/schema.json 與 backend/data/schema_reference.json 保持同步；operations.json 是原有 91 操作索引。
- scene_id 與 daily_phase 不可互相推定。移動動畫只呈現後端結果。中斷在 STREET 時，可依目前階段繼續原目的地。
- EventPanel 包含決策、理賠與籌資；圖片以 visual_key 對照 public/event-media.json。
- Advance 的 opening_snapshot、closing_snapshot、summary 由後端回傳；前端不自行反推期初金額。
- CORS、跨來源登入及 PDF 已做 HTTP／真實客戶端測試；瀏覽器實際點擊與畫面截圖仍未驗收。

素材對照文件保留於此目錄，其圖像路徑沿用組員版本。原始素材包對「50 項測試」的歷史描述不作為本次驗證結果。
