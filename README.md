# Firecrawl 網頁爬蟲工具

使用 [Firecrawl](https://firecrawl.dev/) API 爬取網站內容的 Web 應用程式，支援斷點續傳功能。

## 功能特色

- **Web 操作介面**：直覺的深色主題界面，即時顯示爬取進度
- **斷點續傳**：任務失敗或取消後，可從已爬取的頁面繼續
- **即時狀態更新**：自動輪詢顯示爬取進度
- **資料匯出**：將爬取結果匯出為 JSON 檔案
- **頁面預覽**：支援 Markdown 和 HTML 兩種格式預覽
- **持久化儲存**：任務狀態自動存儲到磁碟，重啟後可恢復

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定 API Key

可透過環境變數或 Web 介面設定：

```bash
export FIRECRAWL_API_KEY="fc-your-api-key"
```

或啟動後在 Web 介面的「API 設定」區塊輸入。

### 3. 啟動伺服器

```bash
python app.py
```

伺服器將在 `http://localhost:5000` 啟動。

## API 清單

### 設定相關

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/api/config` | 檢查 API Key 是否已設定 |
| `POST` | `/api/config` | 設定 Firecrawl API Key |

### 爬取任務

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/api/crawl` | 建立新的爬取任務 |
| `GET` | `/api/crawl/<job_id>` | 取得特定任務的狀態 |
| `POST` | `/api/crawl/<job_id>/resume` | 斷點續傳（從已爬取頁面繼續） |
| `POST` | `/api/crawl/<job_id>/cancel` | 取消進行中的任務 |
| `GET` | `/api/crawl/<job_id>/export` | 匯出任務的完整爬取資料（JSON） |

### 頁面資料

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/api/crawl/<job_id>/pages` | 取得任務的已爬取頁面列表（支援分頁） |
| `GET` | `/api/crawl/<job_id>/page/<page_idx>` | 取得單一頁面的詳細內容 |

### 任務列表

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/api/jobs` | 列出所有爬取任務 |

---

## API 詳細說明

### `GET /api/config`

檢查 Firecrawl API Key 是否已設定。

**回應範例：**
```json
{
  "api_key_set": true,
  "api_key_preview": "fc-xxxxx..."
}
```

### `POST /api/config`

設定 Firecrawl API Key。

**請求 Body：**
```json
{
  "api_key": "fc-your-api-key"
}
```

### `POST /api/crawl`

建立新的爬取任務。

**請求 Body：**
```json
{
  "url": "https://trueway.adholic.com.tw/",
  "limit": 100,
  "formats": ["markdown", "html"]
}
```

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `url` | string | (必填) | 目標網址 |
| `limit` | integer | 100 | 最大爬取頁數 |
| `formats` | array | `["markdown", "html"]` | 輸出格式 |

**回應範例：**
```json
{
  "job_id": "a1b2c3d4",
  "status": "starting"
}
```

### `GET /api/crawl/<job_id>`

取得任務狀態。

**回應範例：**
```json
{
  "job_id": "a1b2c3d4",
  "url": "https://trueway.adholic.com.tw/",
  "status": "crawling",
  "created_at": "2026-04-20T15:00:00",
  "updated_at": "2026-04-20T15:01:00",
  "completed": 15,
  "total": 50,
  "error": null,
  "page_count": 12
}
```

**狀態值：**
- `starting` - 任務正在啟動
- `crawling` - 正在爬取中
- `scraping` - 正在取得剩餘頁面
- `completed` - 已完成
- `failed` - 失敗
- `cancelled` - 已取消

### `POST /api/crawl/<job_id>/resume`

斷點續傳：基於已爬取的頁面建立新任務，保留先前結果。

**回應範例：**
```json
{
  "job_id": "e5f6g7h8",
  "resumed_from": "a1b2c3d4",
  "existing_pages": 12,
  "status": "starting"
}
```

### `POST /api/crawl/<job_id>/cancel`

取消進行中的任務。

### `GET /api/crawl/<job_id>/pages`

取得已爬取頁面列表，支援分頁。

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `page` | integer | 1 | 頁碼 |
| `per_page` | integer | 20 | 每頁數量 |

### `GET /api/crawl/<job_id>/page/<page_idx>`

取得單一頁面的詳細內容（含 markdown 和 html）。

### `GET /api/crawl/<job_id>/export`

匯出完整爬取資料為 JSON。

### `GET /api/jobs`

列出所有爬取任務。

## 目標網站

預設爬取目標：`https://trueway.adholic.com.tw/`

## 技術架構

- **後端**：Python Flask
- **爬蟲引擎**：Firecrawl API
- **前端**：原生 HTML/CSS/JavaScript（深色主題）
- **資料持久化**：JSON 檔案儲存（`crawl_data/` 目錄）
