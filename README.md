# my-agency-web — 可設定式網頁爬蟲

以 YAML 設定檔驅動的 Python 網頁爬蟲框架。只需編輯設定檔即可定義爬取目標、提取規則、翻頁策略和輸出格式，**無需修改程式碼**。

## 功能特色

- **四種爬蟲模式**：單頁、分頁、遞迴、Sitemap
- **YAML 設定檔驅動**：複製範例設定，修改即可上線
- **多種資料選擇器**：CSS 選擇器、正則表達式
- **資料處理管線**：去除空白、清除 HTML、欄位去重
- **多格式輸出**：JSON / CSV
- **反偵測機制**：User-Agent 輪替、請求間隔、自動重試
- **環境變數覆寫**：不改檔案也能調整設定

## 快速開始

### 1. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2. 建立設定檔

```bash
# 複製預設設定
cp crawler/config/default.yaml my_site.yaml

# 或從範例開始
cp crawler/config/example_blog.yaml my_blog.yaml
cp crawler/config/example_ecommerce.yaml my_shop.yaml
```

### 3. 編輯設定檔

打開 YAML 設定檔，修改以下關鍵項目：

```yaml
name: "my-crawler"
mode: "pagination"              # 選擇爬蟲模式

urls:
  - "https://target-site.com/list"

rules:                           # 定義要提取的欄位
  - field: "title"
    selector: "h1.title"
    type: "css"
    first: true
```

### 4. 執行

```bash
python main.py -c my_site.yaml
```

## 爬蟲模式說明

### `single_page` — 單頁模式

爬取一或多個指定 URL，適合產品詳情頁、文章頁。

```yaml
mode: "single_page"
urls:
  - "https://example.com/article/1"
  - "https://example.com/article/2"
```

### `pagination` — 分頁模式

自動翻頁爬取列表，支援兩種策略：

**策略一：「下一頁」連結**

```yaml
mode: "pagination"
urls:
  - "https://example.com/list"
pagination:
  next_page_selector: "a.next"
  max_pages: 20
  items_selector: "div.item"
  item_rules:
    - field: "title"
      selector: "h3"
      type: "css"
      first: true
```

**策略二：URL 模板翻頁**

```yaml
mode: "pagination"
pagination:
  url_template: "https://example.com/list?page={page}"
  start_page: 1
  end_page: 50
```

### `recursive` — 遞迴模式

從起始 URL 自動跟隨連結深度爬取，適合全站抓取。

```yaml
mode: "recursive"
urls:
  - "https://example.com/"
recursive:
  max_depth: 3
  max_pages: 200
  same_domain: true
  url_pattern: "/blog/.*"       # 只爬取 blog 路徑
```

### `sitemap` — Sitemap 模式

從 sitemap.xml 取得 URL 列表後逐一爬取。

```yaml
mode: "sitemap"
sitemap:
  sitemap_url: "https://example.com/sitemap.xml"
  max_pages: 500
  url_pattern: "/product/.*"
```

## 資料提取規則

```yaml
rules:
  # CSS 選擇器 — 取文字
  - field: "title"
    selector: "h1.title"
    type: "css"
    first: true

  # CSS 選擇器 — 取屬性
  - field: "link"
    selector: "a.main-link"
    type: "css"
    attr: "href"
    first: true

  # CSS 選擇器 — 取多筆（返回列表）
  - field: "tags"
    selector: "span.tag"
    type: "css"
    first: false

  # 正則表達式
  - field: "price"
    selector: "\\$([\\d,.]+)"
    type: "regex"
    first: true

  # 取 innerHTML
  - field: "body_html"
    selector: "div.content"
    type: "css_html"
    first: true
```

## 資料處理管線

```yaml
pipeline:
  steps:
    - "strip_whitespace"          # 去除前後空白
    - "remove_empty_fields"       # 移除空值欄位
    - "clean_html_tags"           # 清除 HTML 標籤
    - "deduplicate_by:title"      # 按 title 欄位去重
```

## 引擎設定

```yaml
engine:
  timeout: 30                    # 請求逾時（秒）
  max_retries: 3                 # 重試次數
  request_delay: 1.5             # 請求間隔（秒）
  random_delay: true             # 隨機延遲
  rotate_user_agent: true        # UA 輪替
  proxy: "http://127.0.0.1:7890" # 代理
  headers:
    Cookie: "session=abc123"
```

## 環境變數覆寫

不修改設定檔也能調整參數：

```bash
CRAWLER_ENGINE_TIMEOUT=60 python main.py -c my_site.yaml
CRAWLER_ENGINE_REQUEST_DELAY=3 python main.py -c my_site.yaml
```

## 輸出格式

```yaml
export:
  format: "both"                 # json / csv / both
  output_dir: "./output"
  filename: "results"
```

## 專案結構

```
.
├── main.py                      # CLI 入口
├── requirements.txt             # Python 依賴
├── crawler/
│   ├── engine.py                # HTTP 請求引擎
│   ├── parser.py                # HTML 解析器
│   ├── pipeline.py              # 資料處理管線
│   ├── runner.py                # 執行器（整合所有模組）
│   ├── config/
│   │   ├── loader.py            # 設定檔載入器
│   │   ├── default.yaml         # 預設設定檔
│   │   ├── example_blog.yaml    # 部落格範例
│   │   └── example_ecommerce.yaml # 電商範例
│   ├── modes/
│   │   ├── single_page.py       # 單頁模式
│   │   ├── pagination.py        # 分頁模式
│   │   ├── recursive.py         # 遞迴模式
│   │   └── sitemap.py           # Sitemap 模式
│   └── exporters/
│       ├── json_exporter.py     # JSON 匯出
│       └── csv_exporter.py      # CSV 匯出
└── output/                      # 預設輸出目錄
```
