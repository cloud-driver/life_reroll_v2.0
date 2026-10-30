# Life Reroll v2.0｜人生讀檔與講師工作室

以生活事件、資金安排與保險判斷進行教學的 React／FastAPI 專案，包含原版三輪人生、免登入 Demo，以及可由講師自行編課的通路情境訓練。

此儲存庫提供原始碼、遊戲圖片、內容資料、模型參數、測試與設定範本。**不包含玩家存檔、授課原檔、既有測試帳號、SMTP／LLM 私有設定或建置產物。** 第一次從 GitHub 下載後需要安裝依賴並建置前端。

## 目前功能

- 原版人生：場景移動、工作與月結算、股票／存款／借款／模擬保單、事件選擇、理賠／籌資、人生回顧與回溯。
- AI 人生教練與回顧、以當下資料計算的危機雷達、結束後的人生分岔預演；模型不直接操作遊戲。
- 講師流程：**教材與商品 → 教案工作區 → AI 編課與發布 → 班次與成效**，每頁有上一步／下一步及 12 步實際頁面導覽。
- PDF／DOCX／PPTX／TXT／Markdown 背景解析；手動編課或選用 AI 生成，核對來源與答案後發布固定版本，再開班並查看成效。
- 教案、來源與學員進度依帳號隔離；版本檢查、CSRF／Bearer 及原請求識別保護寫入與安全重試。
- 來源未選／超限／失效、教材限制、AI 狀態、連線及下載錯誤分開顯示。
- 可選的 Tailscale 手機私有入口，網站與 API 使用同來源代理。

這是教育模擬；保費、保障、投資與事故安排是教學假設，並非正式商品報價、投保建議或理賠承諾。AI 內容須由講師核對。

## 目錄

```text
backend/
  app/                  FastAPI、帳號、權威遊戲與訓練引擎
  data/                 遊戲內容、API 契約與雷達模型參數
  scripts/              講師授權、內容建置與模型訓練工具
  tests/                離線後端回歸
  ai-config.example.json
  mail-config.example.json
life-reroll-frontend-20261016-212920/
  components/           React 遊戲與訓練畫面
  lib/                  API client、型別、契約與前端驗證
  public/               執行時使用的圖片／圖示
  source-assets/        圖片原始素材；不會被網站公開服務
  tests/                TypeScript client 整合與錯誤檢查
  serve.py              建置後靜態網站與 API 代理
scripts/                Tailscale 私有入口
start-training-local.command
start-training-tailscale.command
deploy/                 低資源部署與反向代理範本
docs/                   可攜式開發／模型協定說明
TRAINING.md             講師與學員操作、教材及規則
```

前端保留原整合時的目錄名稱，以保持現有啟動、測試與部署路徑相容。前端基礎源自 `D4rk-N355/life_reroll_fronted` 的 `c08d268dbbbcde0b3a113a0128106c2ed8c96ec6`，保留原地圖、車輛、場景與事件素材。

## 第一次安裝

需求：Python 3.11+、Node.js 22.13+ 與 npm。以下命令在專案根目錄執行：

```sh
git clone https://github.com/cloud-driver/life_reroll_v2.0.git
cd life_reroll_v2.0
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-test.txt
cd life-reroll-frontend-20261016-212920
npm ci
npm run typecheck
npm run build
cd ..
```

只執行服務時可改裝 `backend/requirements.txt`；需要測試時使用 `requirements-test.txt`。`requirements-lock.txt` 留存已測套件版本供比對。Windows 可使用虛擬環境的 `Scripts/python.exe` 與下方分開啟動方式。

### macOS 本機訓練

```sh
./start-training-local.command
```

此腳本使用 `backend/training-local.sqlite3`、API `127.0.0.1:8010` 與網站 `127.0.0.1:5180`。首次啟動會建立新資料庫及示範教案，不會匯入任何人的帳號或存檔。

| 入口 | 網址 |
| --- | --- |
| 講師工作室 | http://127.0.0.1:5180/teach |
| 學員訓練 | http://127.0.0.1:5180/training |
| 原版完整人生 | http://127.0.0.1:5180/full |
| 免登入 Demo | http://127.0.0.1:5180/demo |
| 條款／隱私 | http://127.0.0.1:5180/terms ／ /privacy |
| Swagger | http://127.0.0.1:8010/docx |

本機腳本使用明確的 development 郵件模式，不寄出真實郵件。只在本機建立測試帳號且希望略過驗證時，可明確選用：

```sh
LIFE_SKIP_EMAIL_VERIFICATION=1 ./start-training-local.command
```

這個旗標只在 development 郵件模式與 `LIFE_DEVELOPMENT_MODE=1` 同時成立時有效；正式環境應使用 SMTP 驗證。啟動後到 `/full` 自行註冊，再由管理者授予該帳號講師權限：

```sh
LIFE_REPLAY_DB="$PWD/backend/training-local.sqlite3" \
  backend/.venv/bin/python backend/scripts/training_admin.py instructor@example.com
```

把信箱換成自己建立且已驗證的帳號；加 `--revoke` 可撤銷。註冊或一般內容管理角色不會自動取得講師權限。

### 分開啟動／其他平台

完成前端建置後，在兩個終端分別執行：

```sh
cd backend
.venv/bin/python -m app.main --host 127.0.0.1 --port 8000
```

```sh
python3 life-reroll-frontend-20261016-212920/serve.py \
  --host 127.0.0.1 --port 5173 --api-proxy http://127.0.0.1:8000
```

開啟 `http://127.0.0.1:5173/full`。直接啟動 API 預設使用 `backend/game.sqlite3`；可用 `LIFE_REPLAY_DB` 改路徑。原版與訓練都有獨立資料表。

## 手機透過 Tailscale 使用

Mac 與手機先登入可互通的 Tailscale 網路。`start-training-local.command` 在 Tailscale 已連線時會一併啟動手機入口；本機網站已開啟時可另執行：

```sh
./start-training-tailscale.command
```

腳本會讀取當下的 Mac Tailscale IPv4，印出 `http://<Mac 的 Tailscale IP>:5180/teach` 與 `/training`。**網址必須包含 `:5180`**，手機的 `127.0.0.1` 代表手機自己。Mac、VPN 與網站需保持執行；目前未設為開機常駐服務。

這個入口只綁定 Tailscale IP，仍使用原帳號登入及同來源 API 代理；不啟用公開 Funnel。私有 HTTP 網站不保證有 `crypto.randomUUID` 或 Clipboard API，客戶端已提供安全亂數與手動複製備援。

## 可選 AI 與 SMTP 設定

未提供私有設定時，AI 保持停用；手動編課、試玩與學員操作仍可使用。

```sh
cp backend/ai-config.example.json backend/ai-config.json
cp backend/mail-config.example.json backend/mail-config.json
```

依自己的服務修改後再啟用；這兩份實際設定會被 Git 忽略。`mail-config.json` 填入 SMTP 與自行產生的 OTP secret，正式服務使用 `LIFE_EMAIL_MODE=smtp`、`LIFE_DEVELOPMENT_MODE=0`。私有設定不得放進前端 `public/` 或 `dist/`。

AI 使用 **Qwen Workspace 自訂 `/chats`、`/responses` NDJSON 協定**，不是 OpenAI Chat Completions。可設定主機及 `fallback_urls`；只在生成送出前選擇備援，送出後中斷不自動重送。環境變數可用 `LIFE_COACH_ENABLED`、`LIFE_COACH_BASE_URL`、`LIFE_COACH_FALLBACK_URLS`、`LIFE_COACH_TIMEOUT`、`LIFE_TRAINING_LLM_ENABLED` 覆寫。

詳細契約、預算與資料邊界見 [Workspace API](docs/WORKSPACE_API.md) 及 [訓練操作](TRAINING.md)。

## 開發與測試

```sh
backend/.venv/bin/ruff check backend && backend/.venv/bin/ruff format --check backend
backend/.venv/bin/python backend/scripts/sync_frontend_contracts.py --check
backend/.venv/bin/python -m pytest backend/tests -q
cd life-reroll-frontend-20261016-212920
npm run format:check
npm run typecheck
npm run test:unit
npm run build
node tests/error-messages.cjs
npm run test:integration
```

`.github/workflows/ci.yml` 在 push／PR 時執行同一組檢查。格式化用 `ruff format backend` 與前端 `npm run format`；大量格式化的 commit 列在 `.git-blame-ignore-revs`，本機可執行 `git config blame.ignoreRevsFile .git-blame-ignore-revs`。

遊戲內容與 API 契約以 `backend/data/` 為唯一來源。修改後執行 `backend/.venv/bin/python backend/scripts/sync_frontend_contracts.py` 複製到前端；不一致時測試與 CI 會失敗。

後端測試與整合測試使用隔離資料庫，正常回歸會停用真實模型與外寄郵件。整合測試會啟動自己的 API／代理並跑完三輪人生，不是針對既有玩家資料執行。最新驗收範圍及模組位置見 [開發說明](docs/DEVELOPMENT.md)。

前端是建置後服務，修改 React 後要重新 build。修改 Python 後重啟相應 API；不要在有背景生成工作或未儲存編輯時直接重啟／重新整理。

## 版本控制與部署

`.gitignore` 排除虛擬環境、node_modules、dist、資料庫與 WAL／SHM、私有設定、金鑰、授課上傳、QA 帳號／截圖／回覆、備份與發行壓縮檔。遊戲內容 JSON、radar 模型、package-lock 與圖片原始素材保留在 Git。

本機完整 `HANDOFF.md`、提供者主機盤點 `LLM.md` 與 `qa/` 仍保留在原電腦，沒有推送；可攜式說明位於本 README、`TRAINING.md` 與 `docs/`。重新 clone 不會帶入舊存檔、帳號或授課材料。

推送 GitHub 不會部署網站。正式部署使用完整建置的 `dist/`、受保護 API 與相應反向代理，並獨立設定 DB、郵件與 AI；見 [部署範本](deploy/README.md)。保存存檔時使用 SQLite 一致性備份，不把測試 DB 覆蓋到正式環境。

## 授權

Copyright © 2026 知與科技，保留所有權利。本儲存庫公開供閱覽，但未授予任何使用、修改或散布權利；詳見 [LICENSE](LICENSE)。授權洽詢：hasaki@hasaki.idv.tw。

使用說明 PDF：[Life_Reroll_使用說明.pdf](Life_Reroll_使用說明.pdf)。
