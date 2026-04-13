# 台灣預售建案備查爬蟲

這個專案提供一個可重跑的爬蟲，專門抓取內政部實價登錄網站中的「預售屋建案備查」資料。

目前已驗證可正確抓到：

- 縣市：臺中市
- 行政區：西屯區
- 筆數：110 筆

## 為什麼不用 `requests` 直接抓

目標頁面 `https://lvr.land.moi.gov.tw/jsp/list.jsp` 雖然可以直接取得 HTML，但真正的資料表是由前端 JavaScript 在頁面載入後動態生成。

此外，該頁在初始化時會先讀取 `localStorage.form-data`。如果沒有先放入正確的查詢條件，前端腳本會先發生錯誤，導致後續清單不會正常載入。

因此本專案採用的穩定做法是：

1. 以 Selenium 啟動 headless Chrome
2. 先寫入 `localStorage.form-data`
3. 重新載入頁面
4. 讓網站原生查詢流程自行產生建案清單
5. 直接從已渲染的表格擷取資料

## 安裝

建議使用 Python 3.12+。

```bash
python3 -m pip install -r requirements.txt
```

## 使用方式

### 抓臺中市西屯區預售屋建案備查

```bash
python3 presale_remark_crawler.py --city 臺中市 --district 西屯區
```

預設會輸出到：

- `results/presale_remark_臺中市_西屯區.csv`
- `results/presale_remark_臺中市_西屯區.json`

### 指定輸出目錄

```bash
python3 presale_remark_crawler.py --city 臺中市 --district 西屯區 --output-dir results
```

## 輸出欄位

輸出欄位與網站清單畫面一致：

1. 建案名稱
2. 坐落街道
3. 起造人
4. 層棟戶數
5. 使用分區
6. 主要用途
7. 主要建材
8. 申報備查期間
9. 自銷售期間
10. 代銷售期間
11. 坐落基地
12. 建照核發日期
13. 建造執照
14. 完成建物第一次登記日期
15. 詳細內容
16. 功能
17. 備註

另外 JSON 也會額外保留：

- `city`
- `district`
- `query_url`
- `fetched_at`
- `count`

## 已產出結果

目前 repo 內已附上臺中市西屯區的實際抓取結果，可直接查看 `results/` 目錄。