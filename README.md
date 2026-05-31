# 🚉 JR / Tokyo Metro Split-Flap Board

終端機裡的 JR／東京地鐵 **翻牌式（split-flap / Solari board）時刻表站牌**模擬器。

每次刷新會先像老火車站、航站樓的機械翻牌那樣亂數翻滾，再逐格鎖定成真實的到站資訊。
20 條路線、資料驅動、可接 ODPT 即時資料，並提供可嵌入 Claude Code 狀態列的單行跑馬燈模式。

![sample](Screenshot%202026-05-31%20at%201.48.13%20PM.png)

```text
+----------------------------------------------------------+
|   JY   山手線  Yamanote Line                             |
|   JY 17                     新  宿                       |
|                  しんじゅく   Shinjuku                   |
|  ◀ 新大久保                ■                   代々木 ▶  |
|  < Shin-Okubo           Shinjuku               Yoyogi >  |
+----------------------------------------------------------+
| 時刻   | 種別       | 行先 (方面)                | 番線  |
|----------------------------------------------------------|
| 15:45  | 各駅停車   | 品川・渋谷方面             | 1     |
| 15:45  | 各駅停車   | 上野・池袋方面             | 2     |
| 15:50  | 各駅停車   | 品川・渋谷方面             | 1     |
| ...    | ...        | ...                        | ...   |
|----------------------------------------------------------|
| Yamanote Line                                src: STATIC |
+----------------------------------------------------------+
```

> 終端機實際輸出帶有各線的官方代表色（山手線綠、銀座線橘、丸ノ内線紅⋯⋯）。

---

## ✨ 功能

- **真實資料**：可接 [ODPT](https://www.odpt.org/)（公共交通開放資料平台）即時時刻表；未設定金鑰時自動回退到內建的真實靜態時刻表。站牌右下角誠實標示資料來源 `src: ODPT` / `src: STATIC`。
- **20 條路線可切換**，全部資料驅動（見下方路線表）。
- **翻牌動畫**：經典 split-flap / Solari board 效果，速度可調。
- **單行跑馬燈模式**：站名釘住、班次捲動，可嵌入 Claude Code 狀態列。
- **CJK 對齊**：以 `east_asian_width` 處理日文全形字佔 2 格的問題，每行精準對齊到固定視覺寬度。

---

## 🚀 快速開始

```bash
# （選用）只有要接 ODPT 即時資料時才需要
pip install requests

# 列出全部 20 條路線與站點
python3 main.py --list

# 全站牌 + 翻牌動畫（預設山手線新宿，每 10 秒刷新；Ctrl-C 結束）
python3 main.py
```

`--station` 接受**英文名、站號或站 id**，大小寫不拘（例：`--station shinjuku`、`--station 17`、`--station JY17`）。

```bash
# 指定路線／站點，渲染一次就結束
python3 main.py --once --line ginza        --station ginza
python3 main.py --once --line keihintohoku --station tokyo --no-flap

# 翻牌速度微調
python3 main.py --line yamanote --station shinjuku --flap-delay 0.15   # 更慢、更機械感
python3 main.py --line yamanote --station shinjuku --flap-steps 8      # 更少格、更俐落

# 單行跑馬燈
python3 main.py --mode statusline --line oedo --station tochomae --columns 70
python3 main.py --mode statusline --line marunouchi --station tokyo --columns 70 --scroll-all
```

---

## 🚇 路線一覽（20 條）

| 代碼 | `--line` key | 路線 | 站數 | 範例站 |
|:----:|------|------|:----:|------|
| JY | `yamanote` | 山手線（環狀）| 30 | `shinjuku` |
| JC | `chuo` | 中央線快速 | 24 | `tokyo` |
| JB | `sobu` | 中央・総武線各駅停車 | 39 | `akihabara` |
| JK | `keihintohoku` | 京浜東北・根岸線 | 47 | `tokyo` |
| JA | `saikyo` | 埼京線 | 19 | `osaki` |
| JS | `shonanshinjuku` | 湘南新宿ライン | 19 | `shinjuku` |
| JO | `yokosuka` | 横須賀線 | 19 | `yokohama` |
| G | `ginza` | 東京メトロ銀座線 | 19 | `ginza` |
| M | `marunouchi` | 東京メトロ丸ノ内線 | 25 | `tokyo` |
| H | `hibiya` | 東京メトロ日比谷線 | 22 | `naka-meguro` |
| T | `tozai` | 東京メトロ東西線 | 23 | `otemachi` |
| C | `chiyoda` | 東京メトロ千代田線 | 19 | `yoyogi-uehara` |
| Y | `yurakucho` | 東京メトロ有楽町線 | 24 | `wakoshi` |
| Z | `hanzomon` | 東京メトロ半蔵門線 | 14 | `shibuya` |
| N | `namboku` | 東京メトロ南北線 | 19 | `meguro` |
| F | `fukutoshin` | 東京メトロ副都心線 | 16 | `wakoshi` |
| A | `asakusa` | 都営浅草線 | 20 | `asakusa` |
| I | `mita` | 都営三田線 | 27 | `meguro` |
| S | `shinjuku` | 都営新宿線 | 21 | `shinjuku` |
| E | `oedo` | 都営大江戸線 | 39 | `tochomae` |

> `--line shinjuku` 指的是**都營新宿線**（地鐵）；JR 線各有獨立 key（`chuo`/`sobu`/…）。

---

## 🛰️ 接 ODPT 即時資料

1. 到 <https://developer.odpt.org/> 免費申請 consumer key。
2. 設環境變數後執行：

```bash
export ODPT_KEY="你的金鑰"
python3 main.py --line yamanote --station shinjuku   # 站牌右下角會顯示 src: ODPT
```

抓不到（無金鑰、API 錯誤、空資料）時會自動回退靜態時刻表並在 stderr 記錄原因，站牌顯示 `src: STATIC`。

> 🔐 金鑰請勿寫進程式或 commit，用環境變數即可（`.env` 已被 `.gitignore` 忽略）。

---

## 📟 接進 Claude Code 狀態列（statusLine）

多行站牌**不適合**狀態列（會佔 16 行），請用單行 `statusline` 模式。它會把站名釘在最左、班次像燈條捲過去：

```text
[JY] 17 新宿 ▸ 15:45 品川・渋谷方面  15:45 上野・池袋方面  15:50 …
```

在 `~/.claude/settings.json`：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/minghsuan/Downloads/JR-timetable/main.py --mode statusline --line yamanote --station shinjuku --columns 80"
  }
}
```

兩個狀態列的本質限制（已在設計內處理）：

1. **非 TTY**：statusLine 指令沒有終端寬度，**必須用 `--columns N` 明確給寬度**，跑馬燈才會捲動。
2. **非計時器驅動**：Claude Code 只在 render（有活動）時才重跑指令，所以跑馬燈是「每次刷新前進一格」而非閒置時平滑流動。捲動偏移量由當前時間推導，因此每次刷新位置都不同。

`--scroll-all` 可改成整行一起捲動（連站名一起跑）。

---

## 🎞️ 翻牌動畫調校

| 旗標 | 預設 | 效果 |
|------|:----:|------|
| `--no-flap` | — | 跳過動畫，直接畫出結果 |
| `--flap-steps N` | 22 | 從全亂到解出的影格數；越大越漸進 |
| `--flap-delay S` | 0.08 | 每影格停留秒數；越大越慢 |

預設整段動畫約 2 秒。動畫「以什麼順序鎖定」由 `jrboard/flap.py` 的 `lock_threshold()` 決定（目前是由左往右擦除＋微抖動），想改成隨機落定或 ease-out 收尾，調這個函式即可，其他模組不用動。

---

## 🏗️ 架構

**資料驅動**：引擎與路線無關，**新增路線 = 在 `jrboard/data/` 丟一個 `<key>.json`，不必改任何程式**。

| 模組 | 職責 |
|------|------|
| `jrboard/width.py` | CJK 全形字 / ANSI 視覺寬度計算與對齊 |
| `jrboard/model.py` | `Line` / `Station` 資料模型，載入 `data/*.json` |
| `jrboard/sources.py` | 時刻表來源（ODPT + 靜態備援，repository pattern）|
| `jrboard/flap.py` | split-flap 翻牌動畫引擎（純函式、可測）|
| `jrboard/render.py` | 站牌 + 時刻表 ANSI 渲染 |
| `jrboard/statusline.py` | 單行跑馬燈 |
| `jrboard/cli.py` | argparse CLI 與刷新排程 |
| `jrboard/data/*.json` | 各路線的站點 + 時刻表資料 |

### 新增一條路線

在 `jrboard/data/` 放一個 `<key>.json`，照既有檔的結構填：

```jsonc
{
  "key": "tokaido",
  "name_jp": "東海道線", "name_en": "Tokaido Line",
  "symbol": "JT",
  "color": { "name": "...", "ansi_fg": "[38;5;208m",
             "ansi_bg": "[48;5;208m[38;5;232m", "hex": "#F68B1E" },
  "operator": "JR-East",
  "odpt_railway": "odpt.Railway:JR-East.Tokaido",
  "loop": false,
  "stations": [
    { "id": "JT01", "number": "01", "name_jp": "東京", "kana": "とうきょう",
      "name_en": "Tokyo", "odpt_station": "odpt.Station:JR-East.Tokaido.Tokyo" }
  ],
  "timetable": {
    "first_train": "04:30", "last_train": "00:30",
    "headway_min": { "weekday": { "7": 5, "8": 4, "...": 0 }, "holiday": { "...": 0 } },
    "directions": [
      { "id": "down", "name_jp": "熱海方面", "via_jp": "横浜方面", "track": "1" },
      { "id": "up",   "name_jp": "東京方面", "via_jp": "品川方面", "track": "2" }
    ]
  }
}
```

存檔後 `python3 main.py --list` 立刻就會出現這條線。

---

## ✅ 測試

```bash
python3 -m pytest tests -q      # 47 tests
```

涵蓋：視覺寬度（CJK＋ANSI）、資料模型（載入／找站／環狀鄰站）、時刻表來源（靜態產生與 ODPT 備援切換）、翻牌（寬度保持、最後一幀完全解出）、狀態列（站名釘住、跑馬燈隨時間前進）。
