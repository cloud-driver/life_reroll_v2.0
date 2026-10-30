# Qwen Workspace 介面與資料邊界

`backend/app/qwen.py` 使用有狀態的 Workspace 自訂 API，不是 OpenAI Chat Completions。服務不隨本儲存庫提供；依自己的部署設定私有 `backend/ai-config.json`。

## 設定

從 `backend/ai-config.example.json` 複製。`enabled` 控制教練，`training_enabled` 控制編課；範本兩者均停用。`base_url` 指向自己的 `/api/v1`，`fallback_urls` 可填依序嘗試的備援，timeout 上限 600 秒。

`LIFE_COACH_BASE_URL` 單獨覆寫時取代整個檔案連線設定，不繼承備援。要同時覆寫備援，明確提供以逗號分隔的 `LIFE_COACH_FALLBACK_URLS`。`LIFE_TRAINING_LLM_ENABLED`、`LIFE_COACH_ENABLED` 可分別覆寫開關。

## 呼叫流程

1. 候選主機健康檢查 `/health`，並以 `POST /chats` 建立本工作獨立對話。
2. 透過 `POST /responses` 接收 NDJSON 串流，更新背景工作進度。
3. 取消只呼叫本工作 chat 的 `/chats/{id}/stop`；完成／取消後封存自己的對話。不切換或卸載共享模型，不停止別人的 chat。

主機切換只發生在生成送出前。送出後串流中斷只標失敗，避免自動重複生成。封存不是永久刪除，上游可能保留紀錄。

## 編課契約

`contract_version: training-author-v1`，輸出 `events`、`extracted_facts`、`unresolved`。事件包含 `id`、`topic`、`title`、`lesson`、`prompt`、`choices`、`correct_id`、`explanation`、`source_ids`、`loss_minor`、`loss_kind`。

教材輸入 JSON 控制在 11,000 字元內，服務輸入上限 12,000 字元，編課輸出上限 2,800 tokens。只允許實際提供的 source id 及已核對的損失金額／類型；不完整 JSON、未知引用或新增未核對效果會拒絕。裁切文字或來源會加入待核對提醒。

工作狀態包含 `WAITING_PROVIDER`、`QUEUED`、`RUNNING`、`COMPLETE`、`APPLIED`、`CANCELLED`、`FAILED`、`INTERRUPTED`。完成仍需講師核對；套用取消舊審核，僅接受未變更的同版本草稿，不能覆寫較新或已發布版本。

教練只使用目前與已發生的遊戲資料，排除帳號／密碼、未來事件排程及隨機種子。search／memory 關閉；前端只連遊戲後端，不直接連模型。模型不能替玩家執行交易、推進時間或發布教案。
