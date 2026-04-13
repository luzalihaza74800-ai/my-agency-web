# 台灣預售建案爬蟲

這個專案提供一個可重現的爬蟲腳本，用來抓取內政部實價登錄網站上的：

- `saleRemark`：預售屋建案備查

目前已實際驗證、可穩定重現的是 **預售屋建案備查** 流程。

## 為什麼你原本的 Selenium/requests 會抓不到資料

`list.jsp?city=...&district=...` 並不會直接把清單資料塞進 HTML。

網站真正的流程是：

1. 先把查詢條件寫進 `localStorage['form-data']`
2. 再載入 `https://lvr.land.moi.gov.tw/jsp/list.jsp`
3. 由頁面初始化程式 `initQuery()` 讀取 `localStorage`
4. 最後再把資料灌進 DataTables

所以：

- 直接 `requests.get(list.jsp)` 只會拿到空表格殼
- 直接等待 `tbody#table-item-tbody` 也不夠
- 正確作法是模擬網站原本的初始化流程

## 專案內容

- `scripts/presale_build_record_crawler.py`
  - 主要爬蟲腳本
  - 會先寫入 `localStorage['form-data']`
  - 再讓網站自己初始化 DataTables
  - 最後直接從 DataTables API 取出完整資料

## 安裝

需要：

- Python 3.10+
- Chrome 或 Chromium

安裝 Python 套件：

```bash
python3 -m pip install -r requirements.txt
```

## 範例：抓台中市西屯區的預售屋建案備查

```bash
python3 scripts/presale_build_record_crawler.py \
  --query-type saleRemark \
  --city-name 臺中市 \
  --town-name 西屯區
```

預設參數：

- 起始年月：民國 `110/7`
- 結束年月：今年 `12` 月

這組預設值目前可抓到西屯區約 `110` 筆建案備查資料，並可包含像是：

- `續森`
- `正直上弦．壹`

## 常用指令

### 1) 抓西屯區建案備查

```bash
python3 scripts/presale_build_record_crawler.py \
  --query-type saleRemark \
  --city-name 臺中市 \
  --town-name 西屯區
```

### 2) 自訂查詢區間

```bash
python3 scripts/presale_build_record_crawler.py \
  --query-type saleRemark \
  --city-name 臺中市 \
  --town-name 西屯區 \
  --start-y 110 \
  --start-m 1 \
  --end-y 115 \
  --end-m 12
```

### 3) 直接使用代碼

```bash
python3 scripts/presale_build_record_crawler.py \
  --query-type saleRemark \
  --city-code B \
  --town-code B06
```

## 輸出格式

程式會同時輸出：

- JSON：保留完整欄位與 meta 資訊
- CSV：方便 Excel / 試算表開啟

預設輸出到 `output/` 目錄，例如：

```text
output/
  saleRemark_B_B06_11007_11512.json
  saleRemark_B_B06_11007_11512.csv
```

## 重要參數

```bash
--query-type saleRemark
--city-name 臺中市
--town-name 西屯區
--city-code B
--town-code B06
--start-y 110
--start-m 7
--end-y 115
--end-m 12
--output-dir output
--output-prefix custom_name
--show-browser
```

## 已驗證的關鍵結論

1. `list.jsp?city=...&district=...` 不是主要資料來源
2. 真正查詢入口是頁面初始化流程與 `localStorage['form-data']`
3. Selenium 可以用，但重點不是點擊，而是先餵正確的 localStorage
4. 抓資料時應直接從 DataTables API 讀完整資料，而不是只抓當前頁 HTML
5. `saleRemark`（預售屋建案備查）已完成端對端驗證；其他模式若要擴充，建議再依網站初始化流程個別調整

## 注意事項

- 如果環境沒有 Chrome，請先安裝 Chrome 或 Chromium
- 第一次執行 Selenium 可能會花一點時間準備 driver
- 若想人工觀察頁面，可加上 `--show-browser`