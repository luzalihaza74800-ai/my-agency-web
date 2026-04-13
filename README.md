# 台灣預售建案爬蟲

爬取內政部[不動產交易實價查詢服務網](https://lvr.land.moi.gov.tw/)的**預售建案備查**及其他實價登錄資料。

## 核心特色

- 使用 **Playwright** 自動化瀏覽器，攔截 `SERVICE/QueryPrice` API 回應取得結構化資料
- 支援四種查詢類型：預售屋建案備查、預售屋買賣、不動產買賣、不動產租賃
- 匯出 **CSV**（Excel 友善的 utf-8-sig 編碼）和 **JSON** 格式
- 完整的命令列介面，支援自訂縣市、區域、時間範圍

## 技術原理

網站的建案資料是由 JavaScript 動態渲染的，用 `requests` 直接抓只會拿到空的 HTML。本爬蟲透過 Playwright 啟動 headless Chromium：

1. 開啟實價登錄首頁
2. 切換到指定的查詢 tab（如「預售屋建案備查」）
3. 以 JavaScript 注入方式設定縣市、區域、時間範圍
4. 點擊搜尋按鈕
5. 攔截 `SERVICE/QueryPrice` API 的 JSON 回應
6. 將原始資料轉換為友善欄位名稱並匯出

## 安裝

```bash
# 安裝 Python 依賴
pip install -r requirements.txt

# 安裝 Chromium 瀏覽器（Playwright 需要）
playwright install chromium
```

## 使用方式

### 基本用法（台中市西屯區預售建案備查）

```bash
python -m presale_crawler
```

### 指定縣市和區域

```bash
python -m presale_crawler --city 台北市 --district 信義區
```

### 查詢預售屋買賣交易

```bash
python -m presale_crawler --city 台中市 --district 西屯區 --type presale
```

### 指定查詢期間（民國年）

```bash
python -m presale_crawler --start-year 110 --end-year 115
```

### 只匯出 CSV

```bash
python -m presale_crawler --format csv -o 台中西屯建案
```

### 列出所有可查詢的縣市

```bash
python -m presale_crawler --list-cities
```

### 列出指定縣市的鄉鎮市區

```bash
python -m presale_crawler --list-towns --city 台中市
```

### 顯示詳細日誌

```bash
python -m presale_crawler -v
```

## 命令列參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--city` | `台中市` | 縣市名稱 |
| `--district` | `西屯區` | 鄉鎮市區名稱 |
| `--type` | `saleremark` | 查詢類型：`saleremark`(建案備查)、`presale`(預售屋買賣)、`biz`(不動產買賣)、`rent`(租賃) |
| `--start-year` | 去年 | 起始民國年 |
| `--start-month` | `1` | 起始月份 |
| `--end-year` | 今年 | 結束民國年 |
| `--end-month` | `12` | 結束月份 |
| `--output`, `-o` | 自動命名 | 輸出檔案路徑 |
| `--format` | `both` | 輸出格式：`csv`、`json`、`both` |
| `--raw` | 否 | 輸出原始 API 欄位（不轉換） |
| `--list-cities` | - | 列出所有可查詢縣市 |
| `--list-towns` | - | 列出指定縣市的鄉鎮市區 |
| `-v` | - | 顯示詳細日誌 |

## 輸出欄位說明

### 預售屋建案備查（saleremark）

| 欄位 | 說明 |
|------|------|
| 建案名稱 | 預售建案的名稱 |
| 基地位置 | 建案所在地址 |
| 申報人/公司 | 建設公司名稱 |
| 申報日期 | 備查申報日期（民國年月日） |
| 建造執照號碼 | 建照號碼 |
| 核發日期 | 建照核發日期 |
| 戶數 | 建案總戶數 |
| 主要建材 | 建築主要結構材料 |
| 履約擔保機制 | 預售屋履約擔保方式 |
| 銷售期間 | 預定銷售時間範圍 |
| 工程進度 | 目前施工進度 |
| 使用分區 | 土地使用分區 |
| 緯度/經度 | 建案地理座標 |

## 專案結構

```
presale_crawler/
├── __init__.py      # 套件初始化
├── __main__.py      # python -m 入口
├── main.py          # CLI 主程式與參數處理
├── scraper.py       # 核心爬蟲（Playwright + API 攔截）
├── adapter.py       # 原始欄位 → 友善欄位轉換
└── exporter.py      # CSV / JSON 匯出
```

## 注意事項

- 每次查詢約需 **15-20 秒**（需啟動瀏覽器並等待頁面載入），請適度使用
- 資料來源為內政部實價登錄公開資訊，僅供參考
- 本工具僅供學習和研究用途

## 授權

MIT License
