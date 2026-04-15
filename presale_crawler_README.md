# 不動產實價爬蟲 — 完整說明文件

## 檔案清單

| 檔案 | 說明 |
|------|------|
| `presale_crawler_full.py` | 主爬蟲程式（預售屋 + 買賣成屋） |
| `presale_web.py` | Flask 網頁伺服器（UI 控制介面） |
| `db.py` | SQLite 資料庫操作模組 |
| `scheduler.py` | 排程器模組 |
| `start_server.sh` | 伺服器啟動腳本 |
| `presale_data.db` | SQLite 資料庫（目前爬取的資料） |

---

## 快速啟動

### 安裝依賴
```bash
pip3 install flask requests pycryptodome
```

### 啟動伺服器
```bash
bash ~/Desktop/start_server.sh
```
→ 瀏覽器開啟 http://localhost:5678

### 停止伺服器
```bash
kill $(cat /tmp/presale_web.pid)
```

---

## 資料庫內容（截至 2026-04-14）

| 資料表 | 筆數 | 說明 |
|--------|------|------|
| buildings | 749 | 預售建案（台中市各區） |
| presale_transactions | 48,482 | 預售成交紀錄 |
| resale_transactions | 242 | 買賣成屋紀錄（台中市西屯區） |

### 已爬取範圍
- **預售屋**：台中市 北屯區(101~115)、南屯區(imported)、西屯區(imported)、全市(進行中 26% / 1481棟)
- **買賣成屋**：台中市 西屯區(114~115年)

---

## 系統架構

### 爬蟲 API 說明（presale_crawler_full.py）

#### 預售屋（三層）
```
Layer 1: /SERVICE/QueryPrice/SaleData/   → 建案清單
Layer 2: /SERVICE/QueryPrice/SaleList/   → 每筆成交
Layer 3: /SERVICE/QueryPrice/detail/     → 交易明細
```

#### 買賣成屋
```
/SERVICE/QueryPrice/{hash}?q={AES加密參數}
```

#### AES 加密
- Key: `lvr.land.moi.gov.tw`
- 雙層 Base64 + OpenSSL EVP_BytesToKey

### 資料庫 Schema

**buildings**
```sql
id, city, town, name, addr, apply, mark, AA11, base, license,
material, purpose, reg_date, apply_date, self_sale, agent_sale,
house_count, sales_status, lat, lon, crawled_at
```

**presale_transactions**
```sql
tx_id, building_id, building_name, addr, trade_date, total_price,
unit_price, area, floor, build_type, layout, trade_target, park_price,
material, purpose, main_area, balcony_area, public_area, park_area,
land_no, land_zone, land_share, park_no, park_type, park_floor, note,
special_flag, crawled_at
```

**resale_transactions**
```sql
tx_id, city, town, addr, community, trade_date, total_price, unit_price,
area, floor, build_type, layout, trade_target, park_price, purpose, age,
elevator, management, urban_zone, lat, lon, main_area, balcony_area,
public_area, park_area, land_no, land_zone, land_share, park_no, park_type,
park_floor, build_structure, complete_year, note, special_flag, ptype, crawled_at
```

**crawl_history**
```sql
id, data_type, city, town, starty, endy, status, bldg_count, tx_count,
started_at, finished_at, error_msg
```

---

## 功能說明

### 網頁 UI（http://localhost:5678）

#### 爬蟲設定 Tab
- **預售屋 / 買賣成屋** 切換
- 縣市、行政區、年份範圍選擇
- 全台模式（自動爬所有縣市）
- 開始爬取 / 停止

#### 歷史紀錄 Tab
- 顯示所有爬取紀錄（含進行中即時計數）
- 預售：建案數 / 成交數即時更新
- 買賣：完成月份數 / 總筆數即時更新

#### 地圖 Tab
- 篩選：資料類型、縣市、行政區、年份
- 行政區只顯示有資料的區域
- 圖例分開顯示預售/買賣數量
- 自動縮放至資料範圍

#### 排程器 Tab
- 設定定期爬取

### 中斷續傳
- 預售屋：每棟完成後存 checkpoint（`~/.presale_crawler/ckpt_presale_*.json`）
- 買賣成屋：每月完成後存 checkpoint（`~/.presale_crawler/ckpt_resale_*.json`）
- 網頁頂部「未完成任務」面板顯示可繼續的任務

### 並行控制
- 最多同時 2 個爬蟲
- 相同城市+範圍不允許重複啟動

---

## 重要技術細節

### 縣市代碼
```python
"台北市":"A", "台中市":"B", "基隆市":"C", "台南市":"D", "高雄市":"E",
"新北市":"F", "宜蘭縣":"G", "桃園市":"H", "嘉義市":"I", "新竹縣":"J",
"苗栗縣":"K", "南投縣":"M", "彰化縣":"N", "嘉義縣":"P", "雲林縣":"Q",
"屏東縣":"T", "花蓮縣":"U", "台東縣":"V", "金門縣":"W", "澎湖縣":"X",
"連江縣":"Z", "新竹市":"O"
```

### 台中市行政區代碼
```
B06=西屯區, B07=南屯區, B08=北屯區, B09=豐原區, B14=梧棲區 ...
```

### 民國日期轉換
API 回傳兩種格式：
- `1140303`（7碼）→ `2025/03/03`
- `114/03/03`（斜線）→ `2025/03/03`

---

## 已知問題與說明

1. **買賣成屋無建案名稱**：政府 API 不提供，只有地址。`community` 欄位通常為空。

2. **town=空白的建案**：全市爬取時，部分建案 town code 未填，分散在各區，不影響實際資料完整性。

3. **Layer 1 重複資料**：已在爬蟲中加入去重（相同 id 的建案只保留一筆）。

4. **API type safety**：`layer3_detail()` / `biz_query_detail()` 偶爾回傳 `list` 而非 `dict`，已加入 `isinstance` 防護。

---

## 開發過程重要修改紀錄

| 日期 | 修改內容 |
|------|---------|
| 2026-04-12 | 初始版本，預售屋三層爬蟲完成 |
| 2026-04-12 | 買賣成屋 API 研究，解密 AES 參數 |
| 2026-04-12 | 補齊約 20 個 API 必要參數修正 HTTP 500 |
| 2026-04-13 | 修正 `roc_to_ad()` 支援 `YYY/MM/DD` 格式 |
| 2026-04-13 | 修正 `list object has no attribute 'get'` 崩潰 |
| 2026-04-13 | 新增最多 2 個並行爬蟲限制 |
| 2026-04-13 | 新增重複範圍自動跳過 |
| 2026-04-13 | 修正歷史紀錄/統計數字在爬取中即時更新 |
| 2026-04-13 | 地圖篩選加入行政區、年份範圍 |
| 2026-04-13 | 行政區下拉改為從 DB 動態載入 |
| 2026-04-13 | 地圖圖例分開顯示預售/買賣數量 |
| 2026-04-13 | 地圖自動縮放至資料範圍 |
| 2026-04-14 | 修正相同範圍重複 Job 防護 |
| 2026-04-14 | 買賣成屋中斷時強制存 checkpoint |
| 2026-04-14 | 修正切換類型時開始按鈕狀態 |
