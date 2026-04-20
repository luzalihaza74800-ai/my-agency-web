# my-agency-web

使用 [Firecrawl](https://www.firecrawl.dev/) 進行網站爬取的工具，附帶網頁操作介面。

## 功能

- **網頁管理介面** — 深色主題 UI，一鍵操作
- **斷點續傳** — 暫停後可從上次位置繼續爬取
- **即時進度** — SSE 推送爬取進度與日誌
- **快速模式** — 略過 JavaScript 渲染，適合重型網頁（如 GIS 地圖）
- **結果檢視** — 在介面上直接瀏覽抓取的 Markdown 內容
- **下載匯出** — 結果可下載為 JSON 檔案
- **重試失敗** — 一鍵重試所有失敗的頁面
- **狀態持久化** — 重啟伺服器後任務狀態自動恢復

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定 API Key

1. 到 [Firecrawl](https://www.firecrawl.dev/) 註冊帳號並取得 API Key
2. 複製 `.env.example` 為 `.env`，填入 API Key：

```bash
cp .env.example .env
# 編輯 .env，填入 FIRECRAWL_API_KEY=你的_API_Key
```

**Cloud Agent 使用者：** 到 [Cursor Dashboard](https://cursor.com) > Cloud Agents > Secrets，新增 `FIRECRAWL_API_KEY`。

### 3. 啟動網頁介面

```bash
python3 crawler_app.py
```

開啟瀏覽器前往 `http://localhost:5000`

### 4. 開始爬取

1. 輸入目標網址
2. 設定頁數上限與爬取深度
3. 選擇是否開啟「快速模式」
4. 點擊「開始爬取」

## 命令列工具

也可以使用命令列工具進行簡單的爬取：

```bash
# 抓取單一頁面
python3 firecrawl_tool.py scrape https://example.com

# 爬取整個網站
python3 firecrawl_tool.py crawl https://example.com --limit 20 --depth 3

# 取得網站 URL 地圖
python3 firecrawl_tool.py map https://example.com
```

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/` | 網頁操作介面 |
| GET | `/api/jobs` | 列出所有任務 |
| POST | `/api/jobs` | 建立新任務 |
| GET | `/api/jobs/:id` | 取得任務狀態 |
| POST | `/api/jobs/:id/pause` | 暫停任務 |
| POST | `/api/jobs/:id/resume` | 續傳任務 |
| POST | `/api/jobs/:id/retry-failed` | 重試失敗頁面 |
| GET | `/api/jobs/:id/results` | 取得爬取結果 |
| GET | `/api/jobs/:id/download` | 下載結果 JSON |
| GET | `/api/jobs/:id/stream` | SSE 即時進度 |
| DELETE | `/api/jobs/:id` | 刪除任務 |
