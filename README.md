# 台灣預售建案爬蟲專案

這個專案已經直接幫你整理成**適合編輯與維護「台灣內政部實價登錄網 - 預售屋建案備查」爬蟲**的版本，並且把你原本 Selenium 卡住的關鍵原因一起釐清。

## 這次確認到的重點

目標頁面：

- `https://lvr.land.moi.gov.tw/jsp/list.jsp`

### 為什麼 `requests` 抓不到資料

因為頁面初始 HTML 只有表格骨架，真正資料不是直接寫在 HTML 裡，而是前端後續再呼叫：

- `GET /jsp/setToken.jsp`
- `GET /SERVICE/QueryPrice/SaleData/<hash>?q=<encrypted>`

所以直接用 `requests.get(list.jsp)` 只能拿到空表格。

### 為什麼你原本 Selenium 也抓不到

這次實測確認，頁面初始化時會直接讀：

- `localStorage["form-data"]`

如果沒有先放好這個查詢設定，頁面 JS 會提早拋錯，導致：

- 縣市/區域選單初始化不完整
- 搜尋流程沒有真正送出
- `tbody` 一直是空的

所以問題**不是單純等太短**，而是**要先建立正確的前端查詢狀態**。

## 已幫你設定完成的內容

- `pyproject.toml`
  - 建立 Python 專案
  - 安裝 `playwright`
  - 設定 CLI 指令 `presale-crawler`
- `src/tw_presale_crawler/cli.py`
  - 可直接抓預售屋建案備查資料
  - 內建縣市 / 行政區代碼解析
  - 直接攔截官方 `SaleData` JSON 回應
  - 可輸出 JSON 與 CSV
- `.cursor/rules/presale-crawler.mdc`
  - 讓後續 AI 編輯爬蟲時自動遵守：
    - 優先找 API / XHR
    - 不盲目加 sleep
    - 保留 debug HTML / JSON
    - 做節流與錯誤處理
- `.gitignore`
  - 忽略輸出資料與快取

## 安裝

這台環境上我已經驗證過需要安裝 Playwright 與 Chromium。你在本機或其他機器可用：

```bash
python3 -m pip install --user -e .
~/.local/bin/playwright install chromium
```

如果你的 `~/.local/bin` 不在 `PATH`，也可以直接用模組方式執行：

```bash
python3 -m tw_presale_crawler.cli --help
```

## 直接執行

### 抓台中市西屯區

```bash
python3 -m tw_presale_crawler.cli \
  --city "臺中市" \
  --district "西屯區" \
  --start-year 110 \
  --start-month 7 \
  --output-dir output/xitun \
  --save-debug-html output/xitun/debug.html \
  --save-debug-json output/xitun/raw.json
```

### 常用參數

- `--city`：縣市名稱，例如 `臺中市`
- `--district`：行政區名稱，例如 `西屯區`
- `--start-year`：民國年，預設 `110`
- `--start-month`：月份，預設 `7`
- `--end-year`：民國年，預設 `115`
- `--end-month`：月份，預設 `12`
- `--output-dir`：輸出目錄，會生成 `presale_projects.json`、`presale_projects.csv`、`metadata.json`
- `--show-browser`：用有畫面的瀏覽器跑
- `--save-debug-html`：保存載入後頁面 HTML
- `--save-debug-json`：保存 API 原始 JSON

## 已驗證的結果

我在雲端機器實測：

### 西屯區，起始期間 `110/07`

- 目前官方回傳約 `110` 筆
- 可抓到像是：
  - `正直上弦．壹`
  - `雅敦蔚山`
  - `遠雄琉蘊`

### 西屯區，起始期間 `113/01`

- 目前官方回傳約 `59` 筆

也就是說，你原本記錄中的「110 筆」不是錯，而是跟**查詢期間**有關；官方資料也會隨時間變動。

## 目前最佳做法

### 最適合的模式

對這個網站，最適合的做法不是純 `requests`，也不是只靠 Selenium 點來點去，而是：

1. 用 **Playwright** 正常初始化頁面狀態
2. 寫入 `localStorage["form-data"]`
3. 觸發頁面載入
4. 直接攔截 `SaleData` 回應 JSON

這樣的優點：

- 比 Selenium 穩定
- 比硬抓 DOM 更容易維護
- 資料結構完整
- 可以保留 debug HTML / JSON
- 之後也更容易擴充成其他縣市、其他行政區

## 程式輸出欄位

目前輸出的資料會保留官方 JSON 的主要欄位，例如：

- `name`：建案名稱
- `addr`：地址 / 區段
- `apply`：起造人 / 申請人
- `house`：戶數
- `AA11`：使用分區
- `pu`：主要用途
- `ma`：主要建材
- `license`：建照號碼
- `chkdate`：備查日期
- `town`：行政區代碼
- `lat` / `lon`：座標

## 如果你想繼續擴充

下一步很適合做的有：

1. 批次抓所有台中市行政區
2. 自動比對新舊資料差異
3. 匯入 SQLite / PostgreSQL
4. 加上重試、排程與每日增量更新
5. 針對單一建案再延伸抓交易明細

## 一句話結論

你這個站的正解是：

**不要只等 `tbody`，而是先建立 `localStorage form-data`，再用 Playwright 攔截官方 `SaleData` JSON。**