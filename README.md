# 台灣預售建案爬蟲

爬取**內政部不動產交易實價查詢服務網**的預售建案資料。

## 功能

- **預售屋建案備查**（`saleremark`）：查詢建案清單，包含建案名稱、地址、建商、戶數、建材、銷售期間等
- **預售屋買賣**（`presale`）：查詢個別預售屋交易紀錄，包含成交價、單價、面積、格局等
- **不動產買賣**（`biz`）：查詢一般不動產買賣成交資料
- **不動產租賃**（`rent`）：查詢不動產租賃資料

## 技術原理

網站的建案資料是透過 JavaScript 動態渲染的，直接用 `requests` 無法取得。本爬蟲使用 **Playwright** 自動化瀏覽器，模擬使用者操作後攔截底層 `SERVICE/QueryPrice` API 的回應，直接取得結構化 JSON 資料。

## 安裝

```bash
pip install playwright
playwright install chromium
playwright install-deps   # Linux 需要安裝系統相依套件
```

## 使用方式

### 查詢預售建案備查（預設）

```bash
python presale_crawler.py --city 台中市 --district 西屯區 --type saleremark
```

### 查詢預售屋買賣交易

```bash
python presale_crawler.py --city 台中市 --district 西屯區 --type presale
```

### 指定查詢期間（民國年）

```bash
python presale_crawler.py --city 台中市 --district 西屯區 --type saleremark \
    --start-year 110 --end-year 115
```

### 查詢其他縣市

```bash
python presale_crawler.py --city 高雄市 --district 鹽埕區 --type biz
python presale_crawler.py --city 台北市 --district 信義區 --type rent
```

### 完整參數說明

```
--city          縣市名稱（預設：台中市）
--district      鄉鎮市區名稱（預設：西屯區）
--type          查詢類型：saleremark / presale / biz / rent（預設：saleremark）
--start-year    起始年（民國年，預設：去年）
--start-month   起始月（預設：1）
--end-year      結束年（民國年，預設：今年）
--end-month     結束月（預設：12）
--output        輸出檔名前綴（預設自動產生）
--json-only     只輸出 JSON
--csv-only      只輸出 CSV
```

## 輸出

程式會在 `output/` 目錄下產生三個檔案：

| 檔案 | 說明 |
|------|------|
| `*_raw.json` | API 原始回應（保留所有欄位） |
| `*.json` | 中文欄位名稱版本 |
| `*.csv` | CSV 格式（可用 Excel 開啟，UTF-8 BOM 編碼） |

## 資料來源

- **網站**：[內政部不動產交易實價查詢服務網](https://lvr.land.moi.gov.tw/)
- **更新頻率**：每月 1 日、11 日、21 日更新
