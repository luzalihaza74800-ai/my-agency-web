# 台灣預售屋建案備查爬蟲

爬取[內政部不動產交易實價查詢服務網](https://lvr.land.moi.gov.tw/jsp/list.jsp)的**預售屋建案備查**資料。

## 技術說明

此網站資料由 JavaScript 動態渲染，直接用 `requests` 只能得到空的 `<tbody>`。本專案透過**逆向工程**分析網站前端 JavaScript，重現其加密機制，直接呼叫後端 REST API，**不需要 Selenium 或 Playwright**。

### 加密機制

網站使用 CryptoJS 加密查詢參數：

```
queryParams → JSON.stringify → AES-256-CBC(key=域名) → Base64 → 再次 Base64
MD5(queryJSON) → URL 路徑
```

- 金鑰：`lvr.land.moi.gov.tw`（網站 Host）
- AES 金鑰派生：OpenSSL EVP_BytesToKey（MD5）
- 每次查詢需取得一次性 Token（`setToken.jsp`）

## 安裝

```bash
pip install -r requirements.txt
```

**相依套件：**
- `requests` — HTTP 請求
- `pycryptodome` — AES 加密（模擬 CryptoJS）

## 使用方式

### 基本查詢

```bash
# 臺中市西屯區（民國 112-113 年，預設）
python3 crawler.py --city 臺中市 --district 西屯區

# 台北市信義區
python3 crawler.py --city 台北市 --district 信義區

# 全市查詢（不指定區域）
python3 crawler.py --city 高雄市
```

### 進階選項

```bash
# 指定查詢年份
python3 crawler.py --city 臺中市 --district 西屯區 --start-year 111 --end-year 113

# 按建商名稱搜尋
python3 crawler.py --city 臺中市 --district 西屯區 --builders 遠雄

# 按路段搜尋
python3 crawler.py --city 臺中市 --district 西屯區 --road 市政北

# 指定輸出格式與檔名
python3 crawler.py --city 臺中市 --district 西屯區 --format csv --output 西屯建案

# 只輸出 JSON
python3 crawler.py --city 台北市 --format json
```

### 完整參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--city` | 縣市名稱 | `臺中市` |
| `--district` | 鄉鎮市區名稱（留空=全市） | `西屯區` |
| `--start-year` | 查詢起始民國年 | `112` |
| `--start-month` | 查詢起始月 | `1` |
| `--end-year` | 查詢結束民國年 | `113` |
| `--end-month` | 查詢結束月 | `12` |
| `--builders` | 建商名稱關鍵字 | |
| `--road` | 路段關鍵字 | |
| `--output` | 輸出檔名（不含副檔名） | 自動生成 |
| `--format` | 輸出格式：`csv`/`json`/`both` | `both` |
| `--delay` | 請求間隔秒數 | `1.0` |
| `--verbose` | 顯示詳細日誌 | |

## 輸出格式

結果儲存於 `output/` 目錄。

### CSV 欄位

| 欄位 | 說明 |
|------|------|
| `name` | 建案名稱 |
| `addr` | 地址 |
| `apply` | 申報建商 |
| `applydate` | 申報日期（民國年月日） |
| `license` | 建照號碼 |
| `house` | 戶數 |
| `pu` | 用途分區 |
| `AA11` | 都市土地使用分區 |
| `ma` | 主要建材 |
| `s` | 銷售期間 |
| `lat` / `lon` | 緯度 / 經度（WGS84） |
| `mark` | 備註 |
| `id` | 建案唯一識別碼 |
| `chkdate` | 最後查核日期 |

### 範例輸出

```
============================================================
查詢結果摘要
============================================================
縣市：臺中市
鄉鎮市區：西屯區
查詢期間：民國 112/01 ~ 113/12
建案總數：79 筆

建案清單（前 10 筆）：
   1. 和宜好好｜西屯區西屯路二段297-8巷12弄｜91 戶｜和宜建設股份有限公司
   2. 遠雄純寓｜西屯區逢大路和凱旋一街交叉口｜128 戶｜遠雄建設事業股份有限公司
   3. 豐蒔｜西屯區市政北七路及惠中一街交叉口｜84 戶｜大陸建設股份有限公司
...
```

## 縣市代碼對照表

| 縣市 | 代碼 | 縣市 | 代碼 |
|------|------|------|------|
| 基隆市 | C | 臺中市 | B |
| 臺北市 | A | 南投縣 | M |
| 新北市 | F | 彰化縣 | N |
| 桃園市 | H | 雲林縣 | P |
| 新竹市 | O | 嘉義市 | I |
| 新竹縣 | J | 嘉義縣 | Q |
| 苗栗縣 | K | 臺南市 | D |
| 高雄市 | E | 屏東縣 | T |
| 宜蘭縣 | G | 花蓮縣 | U |
| 臺東縣 | V | 澎湖縣 | X |
| 金門縣 | W | 連江縣 | Z |

## 注意事項

- 資料來源為政府公開資料，僅供學術研究或個人參考。
- 請勿對伺服器發出過量請求（預設 1 秒間隔）。
- Token 為一次性使用，Session 過期時程式會自動提示。
- 查詢結果因伺服器快取可能與網站稍有差異。
