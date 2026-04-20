# my-agency-web

使用 [Firecrawl](https://www.firecrawl.dev/) 進行網站爬取的工具。

## 設定方式

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 設定 API Key

1. 到 [Firecrawl](https://www.firecrawl.dev/) 註冊帳號並取得 API Key
2. 複製 `.env.example` 為 `.env`，並填入你的 API Key：

```bash
cp .env.example .env
```

然後編輯 `.env` 檔案：

```
FIRECRAWL_API_KEY=你的_API_Key
```

**Cloud Agent 使用者：** 請到 [Cursor Dashboard](https://cursor.com) > Cloud Agents > Secrets，新增名為 `FIRECRAWL_API_KEY` 的 Secret，值為你的 API Key。

## 使用方式

### 命令列工具

```bash
# 抓取單一頁面（回傳 Markdown）
python3 firecrawl_tool.py scrape https://example.com

# 爬取整個網站（限制頁數與深度）
python3 firecrawl_tool.py crawl https://example.com --limit 20 --depth 3

# 取得網站 URL 地圖
python3 firecrawl_tool.py map https://example.com

# 將結果儲存到檔案
python3 firecrawl_tool.py scrape https://example.com -o result.json
```

### 在 Python 中使用

```python
from firecrawl_tool import scrape_url, crawl_url, map_url

# 抓取單一頁面
result = scrape_url("https://example.com")

# 爬取整個網站
result = crawl_url("https://example.com", limit=10, max_depth=2)

# 取得 URL 地圖
urls = map_url("https://example.com")
```

## 功能說明

| 功能 | 說明 |
|------|------|
| `scrape` | 抓取單一頁面，轉換為 Markdown 格式 |
| `crawl` | 從指定 URL 開始爬取多個頁面 |
| `map` | 取得網站所有可存取的 URL 列表 |
