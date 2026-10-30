# 低資源主機部署

已建置的前端約 17.3 MB；伺服器不需要 Node.js、Pillow 或前端開發伺服器。請使用 Python 3.11 以上。遊戲規則、郵件驗證與 AI 的資料邊界保持原設定。

1. 複製 `backend/app`、`backend/data`、`backend/requirements.txt`、`deploy/` 與前端 **完整 `dist/`**。不要把整個專案當成網站根目錄。
2. 建立後端 `.venv`，安裝 requirements。依根目錄 README 設定私有 `mail-config.json`、選用的 `ai-config.json`，以及 `LIFE_REPLAY_DB`。如需沿用玩家進度，先停止舊程序並備份 SQLite（含尚未合併的 WAL）；不要覆蓋成測試資料庫。
3. 執行 `./deploy/start-low-resource.sh`。預設只有 **1 個 API 程序、4 個同步請求執行緒、1 個預演計算工作**；AI／寄信另外使用有上限的背景工作池。可將 `LIFE_REQUEST_WORKERS=2` 降低尖峰記憶體占用。請保持單一 API worker，避免背景工作復原機制誤判。
4. 將 `nginx-locations.conf` 加入既有的 HTTPS `server {}`，修改前端路徑並執行 `nginx -t`。前端 `dist/config.js` 保留同來源 `apiBase: ''`。瀏覽器只接觸 Nginx；8000 留在 loopback。此範例尚未在你的目標伺服器部署。
5. 部署時包含 `.gz` 檔。Nginx 直接讀建置好的壓縮檔，避免弱主機每次壓縮。先以 `nginx -V` 確認 `--with-http_gzip_static_module`；若套件沒有此模組，移除 `gzip_static on`，其餘功能仍可運作。參考 [Nginx 官方文件](https://nginx.org/en/docs/http/ngx_http_gzip_static_module.html)。

`start-low-resource.sh` 限制同時連線，過載時回覆 503；客戶端會保留需要確認的原操作識別，可同步後安全重試，不會自動重複扣款。不要任意加快 AI／預演輪詢，或增加多個 CPU 預演 worker。

本機不使用 Nginx 時，仍可照原本 README 執行 `serve.py`；現已支援預壓縮、ETag／304、HEAD、雜湊檔名長期快取與同來源 API。公開主機建議讓 Nginx 處理靜態檔。

前端重建：`npm ci && npm run build`。圖片已經最佳化，正常重建不需 Pillow。需要替換原圖時，保留原圖於 `source-assets/`，在有 Pillow 的開發環境執行 `python scripts/optimize-images.py` 再 build。`source-assets/`、`node_modules/`、`qa/` 都不需要上傳至網站伺服器。

每份完整人生仍保留帳本與回溯歷史，因此使用者很多時，SQLite、磁碟及記憶體需求仍會增加。本次實測是本機隔離資料庫，不能當作目標主機的容量保證；部署後應用預期同時人數再做負載測試。

## 來源版本與部署狀態

這些檔案是部署範本，Git push 不會更新任何網站。歷史環境使用 `/opt/life-replay/current`、API 18081 與 Nginx 18080；請按自己的主機修改。新訓練／講師工作室、AI 備援及錯誤修正沒有因建立此儲存庫而自動部署。

部署只放完整建置的 dist、API 程式、必要內容及受保護的私有設定。不要將 QA、玩家 DB、授課原檔、私鑰、SMTP 密碼、備份或 node_modules 放進公開網站根。部署前備份自己環境的 SQLite，設定正式郵件、AI 與可達網路，再依預期同時人數驗證容量。
