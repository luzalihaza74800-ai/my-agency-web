# 台灣預售建案備查爬蟲

爬取內政部不動產交易實價查詢服務網的**預售建案備查**資料（開放資料免費下載）。

## 原理說明

本工具**不需要** Selenium 或 Playwright，透過逆向工程分析網站 JavaScript 後，直接呼叫內政部的開放資料 API：

```
GET https://plvr.land.moi.gov.tw/Download
    ?PayType=saleremark
    &fileName={city_code}_lvr_buildcase.csv
```

資料每月 1 日重新產製，包含自 **民國 110 年 7 月 1 日**起申報備查的所有預售屋建案。

---

## 安裝

```bash
pip install -r requirements.txt
```

---

## 使用方式

### 基本用法（預設：台中市西屯區）

```bash
python crawler.py
```

### 指定縣市與區域

```bash
python crawler.py --city 台中市 --district 西屯區
```

### 下載整個縣市（不過濾區域）

```bash
python crawler.py --city 台北市 --no-filter
```

### 指定輸出路徑

```bash
python crawler.py --city 台南市 --district 安平區 --output tainan_anping.csv
```

### 所有參數

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--city` | `台中市` | 縣市名稱 |
| `--district` | `西屯區` | 鄉鎮市區名稱 |
| `--no-filter` | — | 不過濾區域，下載整個縣市 |
| `--output / -o` | 自動命名 | 輸出 CSV 路徑 |
| `--timeout` | `60` | HTTP 請求逾時秒數 |
| `--no-print` | — | 不在終端機印出摘要 |

---

## 輸出資料欄位

| 中文欄位 | 英文欄位 | 說明 |
|----------|----------|------|
| 鄉鎮市區 | TOWN | 行政區 |
| 建案名稱 | BUILDCASE | 建案名稱 |
| 坐落街道 | LOCATION | 地址 |
| 起造人 | BUILDER | 建設公司 |
| 層棟戶數 | HOUSEHOLD | 戶數 |
| 使用分區 | USEZONING | 土地使用分區 |
| 主要用途 | MAINUSE | 建物主要用途 |
| 主要建材 | MAINMATERIAL | 建材 |
| 申報備查日期 | DECLAREDATE | 備查申報日期（民國年月日） |
| 銷售期間 | SELLINGPERIOD | 銷售起訖期間 |
| 坐落基地 | BUILDINGLANDS | 地號 |
| 建照核發日期 | BUILDINGPERMITDATE | 建照核發日期 |
| 建造執照 | BUILDINGPERMITNO | 建造執照號碼 |
| 第1次登記日期 | FIRST REGISTRATION DATE | 首次登記日期 |
| 編號 | NUMBER | 系統編號 |

---

## 支援縣市

| 代碼 | 縣市 |
|------|------|
| A | 臺北市 |
| B | 臺中市 |
| C | 基隆市 |
| D | 臺南市 |
| E | 高雄市 |
| F | 新北市 |
| G | 宜蘭縣 |
| H | 桃園市 |
| I | 嘉義市 |
| J | 新竹縣 |
| K | 苗栗縣 |
| M | 南投縣 |
| N | 彰化縣 |
| O | 新竹市 |
| P | 雲林縣 |
| Q | 嘉義縣 |
| S | 屏東縣 |
| T | 花蓮縣 |
| U | 臺東縣 |
| V | 澎湖縣 |
| W | 金門縣 |
| X | 連江縣 |

---

## 技術說明

### 為什麼 requests 直接抓網頁會是空的？

`https://lvr.land.moi.gov.tw/jsp/list.jsp` 是動態網頁，建案資料透過加密的 AJAX 請求取得，流程如下：

1. 網頁用 CryptoJS AES 將查詢參數加密（key = `window.location.host`）
2. 呼叫 `../SERVICE/QueryPrice/SaleList/{hash}?q={encrypted_params}`
3. 伺服器回傳 JSON，再由 JavaScript 渲染成表格

### 本工具的解法

繞過上述流程，直接使用內政部提供的**開放資料 API**：

```
https://plvr.land.moi.gov.tw/Download?PayType=saleremark&fileName={city_code}_lvr_buildcase.csv
```

此端點無需加密、無需認證，直接回傳 CSV 格式，資料來源與網站完全一致。

---

## 資料授權

本工具下載之資料屬**政府開放資料**，授權條款請參閱[內政部不動產資料供應系統](https://plvr.land.moi.gov.tw/DownloadOpenData)。
