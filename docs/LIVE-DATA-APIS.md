# 即時列車資料 API 選擇（ODPT 以外）

> 為 jrboard 的 live service layer 評估的資料來源。日期 2026-06-07。
> 評估準則：(1) 有沒有**即時誤點/運行情報**；(2) 授權與費用（免費/商用）；(3) 是否契合 jrboard 的**零依賴 + optional `[live]`**架構（能用 `requests` 抓 JSON/protobuf 就好）。

## TL;DR 建議
- **即時資料首選：GTFS-Realtime（開放、標準、免費）** — 多數首都圈業者（含 JR East）已透過「公共交通オープンデータセンター」釋出 GTFS + GTFS-RT。標準格式、不綁單一供應商，最適合做成 jrboard 的 realtime tier。ODPT 其實就是這個生態的一員。
- **靜態路線/車站擴充：HeartRails Express + ekidata.jp（皆免費）** — 想把 jrboard 從現有 JSON 擴到全日本路線/車站，這兩個免費 API 是最便宜的資料來源（無即時，但補齊 static JSON 很夠）。
- **商用路徑規劃才考慮：Ekispert / NAVITIME** — 功能最全（轉乘、票價、跨海陸空），但**付費**且需洽談，對一個終端玩具型工具過重。

---

## 比較表

| 來源 | 即時誤點 | 時刻表 | 車站/路線 metadata | 授權/費用 | 契合度 | 備註 |
|------|:---:|:---:|:---:|------|------|------|
| **ODPT**（現用） | ✅ | ✅ | ✅ | 免費需 key | ★★★ | 首都圈為主；StationTimetable 已接，誤點在 TrainInformation 端點 |
| **GTFS-RT（業者開放）** | ✅ | ✅(GTFS) | ✅ | 免費 | ★★★ | 標準格式；JR East 提供 GTFS+GTFS-RT；需解 protobuf（或用 JSON 鏡像） |
| **Transitland REST API** | ✅(聚合) | ✅ | ✅ | 免費/註冊 | ★★☆ | 聚合全球 GTFS/GTFS-RT，含日本（目前以巴士為主）；純 REST/JSON 最好接 |
| **Ekispert API**（ヴァル研究所） | 部分 | ✅ | ✅ | **商用付費** | ★☆☆ | 路徑/票價/全國涵蓋最強；需授權費（含時刻表 DB 授權） |
| **NAVITIME API** | ✅ | ✅ | ✅ | **商用付費**（部分上 RapidAPI） | ★☆☆ | 涵蓋海陸空多模式；最完整但最貴 |
| **HeartRails Express** | ❌ | ❌ | ✅ | **免費**（商用亦可） | ★★☆ | XML/JSON(P)；area→都道府縣→路線→車站→最寄駅；純補 static |
| **ekidata.jp（駅データ.jp）** | ❌ | ❌ | ✅ | 免費（會員） | ★★☆ | 路線/車站 CSV+API；擴充 jrboard 的線路 JSON 最直接 |
| **TokyoGTFS（社群）** | — | ✅(GTFS) | ✅ | 開源 | ★★☆ | 把首都圈資料轉成乾淨 GTFS 的工具/產物，可離線預生成 jrboard JSON |
| **Google Maps Transit / Directions** | ✅ | ✅ | ✅ | 付費（額度） | ★☆☆ | 全球；但綁 Google、計費、ToS 較嚴，離終端工具調性遠 |

---

## 接進 jrboard 的策略（依現有架構）

jrboard 已有 `sources.py` 的 `TimetableSource` protocol + `Departure.delay_min/alert_text` 接縫，所以新來源只要實作 `departures()` 並填那兩個欄位即可。建議分層（與本次做的 cache + alerts overlay 疊起來）：

1. **realtime tier — GTFS-RT**：新增 `GtfsRtSource`，抓業者的 GTFS-RT `TripUpdate`/`Alert`，填 `delay_min`/`alert_text`。GTFS-RT 是 protobuf，會引入 `protobuf` 依賴 → 放進 `extras_require` 的 `[live]`（或抓已轉 JSON 的鏡像端點避免依賴）。
2. **static 擴充 — ekidata.jp / HeartRails**：寫一個**離線產生器腳本**（`scripts/`），把全日本路線/車站抓下來轉成 jrboard 的 `data/*.json`。一次性、不進執行期依賴，完美契合「加線=丟 JSON」的零依賴本質。
3. **聚合備援 — Transitland**：覆蓋業者沒自釋的線；純 REST/JSON，最好接，當 ODPT/GTFS-RT 的 fallback tier（接在現有 source chain 後面，用 `src:` 徽章標示）。

> 來源鏈建議：`GTFS-RT → ODPT → Transitland → CACHE → STATIC`，每層都用既有的 `src:` 標籤誠實標示資料來源。

---

## Sources
- [Open Data Challenge for Public Transportation 2025 (ODPT)](https://challenge2025.odpt.org/en/opendata.html)
- [Public Transportation Open Data Center — overview](https://www.odpt.org/en/overview/)
- [GTFS Realtime list in Japan (taisukef gtfs-map)](https://taisukef.github.io/gtfs-map/list.html)
- [TokyoGTFS (GitHub, MKuranowski)](https://github.com/MKuranowski/TokyoGTFS)
- [Transitland REST API — Feeds](https://www.transit.land/documentation/rest-api/feeds)
- [Transitland — inspect GTFS-Realtime](https://www.interline.io/blog/easily-inspect-gtfs-realtime-using-transitlands-website-or-api/)
- [Ekispert API (AltStack)](https://altstack.jp/en/services/map-apis/ekispert-api/) · [Ekispert API ToS (PDF)](https://docs.ekispert.com/v1/WebService_TOS_en.pdf)
- [HeartRails Express API](http://express.heartrails.com/api.html)
- [ekidata.jp 路線API](https://ekidata.jp/api/api_line.php)
- [open-data-jp-railway-stations (GitHub, piuccio)](https://github.com/piuccio/open-data-jp-railway-stations)
