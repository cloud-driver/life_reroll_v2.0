# 加入事件圖片

## 建議方式：依事件編號命名

1. 查看 `docs/EVENT_IMAGE_INDEX.md`，找到圖片所屬的事件卡編號。
2. 將圖片放進 `public/events/`，用編號命名，例如 `FA06.webp`、`CH10.png`。
3. 從專案根目錄執行 `pnpm sync:event-images`。
4. 重新整理遊戲，對應事件發生時就會顯示圖片。也可從事件歷史查看已發生的對應事件。

| 事件 | 圖片範例 | 網頁路徑 |
| --- | --- | --- |
| FA06 肉包鐵的代價 | `public/events/FA06.webp` | `/events/FA06.webp` |
| CH10 無薪加班過勞 | `public/events/CH10.png` | `/events/CH10.png` |
| FA25 意外滑倒 | `public/events/FA25.jpg` | `/events/FA25.jpg` |

支援 WebP、PNG、JPG、JPEG、AVIF。建議橫向 16:9，例如 1600 × 900；圖片會在事件區等比例完整顯示，不裁切。建議壓縮至約 500 KB 以下，以減少讀取時間。每個事件編號只放一張圖片；若有多種格式，工具依 WebP、AVIF、PNG、JPG、JPEG 的順序選一張。

同步工具會更新 `public/event-media.json` 的 `events` 對應，保留沒有改動的既有事件設定及 `kinds` 通用圖片。不需要改 Python，也不需要重開一輪人生。

## 保留原檔名：手動對應

如果圖片原本叫 `motorcycle-fracture.webp`，可保留檔名，放入 `public/events/`，再於 `public/event-media.json` 的 `events` 物件內加入：

```json
"FA06": {
  "src": "/events/motorcycle-fracture.webp",
  "alt": "騎車摔傷後接受治療的情境"
}
```

不要刪除原本的 `kinds`。網頁路徑不包含 `public`，也不要填 `C:\...` 或 `D:\...` 磁碟路徑。這是物件內的一筆設定；有多筆時須用逗號分隔，最後一筆後面不加逗號。

## 圖片選擇順序

1. `events[visual_key]`：事件專屬圖片，最高優先，包括醫院事件。
2. 醫院連動事件未設定專屬圖片時，使用 `kinds.HEALTH`。
3. 其他事件使用所屬 `kinds` 的通用圖片。
4. 未設定或圖片載入失敗時顯示預留區；事件結算仍正常。

`visual_key` 是固定事件卡編號，例如 `FA06`。不要用每次遊戲隨機產生的 `event.id`。種類包括 CAREER、FAMILY、HEALTH、ACCIDENT、MARKET、POLICY、EXPENSE。

可以先開啟 `http://127.0.0.1:5173/events/FA06.webp` 確認圖片可讀取。若事件仍顯示通用圖，請檢查編號與副檔名、重新執行同步指令，再按 Ctrl + Shift + R。

## 開發接口

組件為 `components/game/event-media.tsx`。事件畫面和回顧共用 manifest。呼叫者可用 `asset={{src,alt}}` 明確覆寫；目前就醫事件不再硬性覆寫專屬圖片。

`life-reroll:event-media` CustomEvent 的 detail 包含 run_id、event_id、visual_key、kind、occurred_on、status。這是呈現通知，不是結算接口；不可用來重複扣款或提交理賠。
