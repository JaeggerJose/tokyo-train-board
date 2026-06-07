# 🚉 JR / Tokyo Metro Split-Flap Board

[English](README.en.md) · **繁體中文** · [日本語](README.ja.md)

[![PyPI](https://img.shields.io/pypi/v/tokyo-train-board)](https://pypi.org/project/tokyo-train-board/)
[![Python](https://img.shields.io/pypi/pyversions/tokyo-train-board)](https://pypi.org/project/tokyo-train-board/)
[![CI](https://github.com/JaeggerJose/tokyo-train-board/actions/workflows/ci.yml/badge.svg)](https://github.com/JaeggerJose/tokyo-train-board/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

終端機裡的 JR／東京地鐵 **翻牌式（split-flap / Solari board）時刻表站牌**模擬器。

```bash
pip install tokyo-train-board && jrboard
```

每次刷新會先像老火車站、航站樓的機械翻牌那樣亂數翻滾，再逐格鎖定成真實的到站資訊。
20 條路線、資料驅動、可接 ODPT 即時資料，並提供可嵌入 Claude Code 狀態列的單行跑馬燈模式。

![demo](demo.gif)

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

## 🧩 更多模式：TUI、番茄鐘、通勤守門員、行事曆

除了站牌與跑馬燈，同一支 CLI 還提供四種附加模式（所有舊旗標行為不變，這些都是選用）。

```bash
# 互動式 curses 瀏覽器：左邊是「依城市分組」的路線清單（各線官方色，
# j/k 移動、/ 模糊搜尋、h/l 切換站點、f 收藏、q 離開），右邊是即時彩色站牌
# （切換線/站時會播翻牌動畫）
python3 main.py --tui

# 番茄鐘＝一趟電車旅程：把專注計時畫成從起點到終點的乘車。會在路線上
# 自動挑兩站（或用 --from/--to 指定），先播翻牌動畫，之後每秒重繪，
# 直到「とうちゃく」（抵達）。
python3 main.py --pomodoro 25 --line yamanote
python3 main.py --pomodoro 25 --line yamanote --from shinjuku --to tokyo
python3 main.py --pomodoro 1 --line yamanote --once   # 只畫一格就結束

# 通勤守門員：「我幾點要出門才趕得上下一班車？」需要在設定檔填
# [commute] home/work（見下）。早上 → 家→公司，下午／晚上 → 公司→家。
python3 main.py --commute                       # 完整站牌
python3 main.py --commute --mode statusline     # 精簡單行

# 行事曆來源：用本機 .ics 檔當作發車來源（標籤 AGENDA），把接下來的
# 會議當成電車顯示，而非時刻表。
python3 main.py --feed-ics ~/cal.ics --once
python3 main.py --feed-ics ~/cal.ics --mode statusline --columns 70
```

### 設定檔

設定讀自 `~/.config/jrboard/config.toml`（會尊重 `XDG_CONFIG_HOME`）。檔案缺失或格式錯誤會直接忽略——一律套用預設值，而 CLI 旗標永遠覆寫設定檔。

```toml
[board]
line = "oedo"
station = "tochomae"
columns = 50
width = 60
flap_steps = 22
flap_delay = 0.08

[commute]
home = ["yamanote", "shinjuku"]
work = ["yamanote", "tokyo"]
leave_buffer_min = 7      # 走到車站的緩衝分鐘數
```

在 TUI 中切換的收藏會存到 `~/.config/jrboard/favorites.txt`（每行一組 `line_key,station_key`）。

### 安裝／進入點

```bash
pip install -e .        # 安裝 `jrboard` 命令列腳本
jrboard --list          # 與 `python3 main.py` 相同的 CLI
jrboard --tui
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

### 🌏 其他城市（京都／大阪／札幌／小樽）

用 `--city` 篩選城市：`python3 main.py --list --city Osaka`；`--rotate --city Osaka` 只在大阪境內隨機巡迴。

| key | 城市 | 路線 | 站數 |
|------|:----:|------|:----:|
| `osaka-loop` | 大阪 | JR 大阪環狀線（環狀）| 19 |
| `osaka-midosuji` | 大阪 | 御堂筋線 | 20 |
| `osaka-tanimachi` | 大阪 | 谷町線 | 26 |
| `kyoto-karasuma` | 京都 | 地下鐵烏丸線 | 15 |
| `kyoto-tozai` | 京都 | 地下鐵東西線 | 17 |
| `kyoto-randen` | 京都 | 嵐電 嵐山本線（路面電車）| 13 |
| `kyoto-sagano` | 京都 | JR 嵯峨野線（山陰本線）| 15 |
| `kyoto-keihan` | 京都 | 京阪本線 | 42 |
| `sapporo-namboku` | 札幌 | 南北線 | 16 |
| `sapporo-tozai` | 札幌 | 東西線 | 19 |
| `sapporo-toho` | 札幌 | 東豊線 | 14 |
| `otaru-hakodate` | 小樽 | JR 函館本線（小樽—札幌）| 15 |

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
5h 20%·7d 27%·ctx 50% [JY] 17 新宿 ▸ 15:45 品川・渋谷方面  15:45 上野・池袋方面 …
```

### 一鍵安裝（最推薦，任何有 python3 的機器都能跑）

本專案**零執行期依賴**，所以根本不需要 pip。下面這行會自動偵測管道（`pip --user` → `pipx` → **git clone 直跑必勝回退**），再把 statusLine 寫進 `~/.claude/settings.json`：

```bash
curl -fsSL https://raw.githubusercontent.com/JaeggerJose/tokyo-train-board/main/install.sh | bash
# 客製：加旗標（會轉給 install-statusline）
curl -fsSL .../install.sh | bash -s -- --columns 90 --line oedo --city Tokyo --csl
```

旗標：`--csl`（順便裝 csl 主題）、`--offline`（強制 clone、可改原始碼）、`--no-statusline`（只裝工具、不碰 settings.json）。

> 為什麼用 bootstrap：在 minimal Debian/Ubuntu 24.04 上，`pip`／`venv`／`pipx` **預設都沒裝**，且 PEP 668 鎖死系統 pip——三條 pip 路徑都得先 `sudo apt`。clone 回退靠 stdlib 直接跑 `main.py`，**免 pip、免 venv、免 sudo**，這才是真正萬用的路。

### 一鍵安裝（pip 已可用時）

```bash
pip install tokyo-train-board       # 或 pipx install tokyo-train-board
jrboard install-statusline          # 把 statusLine 寫進 ~/.claude/settings.json（自動備份、保留其他設定）
```

> `install-statusline` 用 `<你的python> -m jrboard` 產生指令，所以**即使 `jrboard` 不在 PATH 也能跑**（`pip install --user` 會把它放到不在 PATH 的 `~/.local/bin`）。可加 `--columns 90`、`--line oedo`、`--city Tokyo`、`--mode minitable` 客製。移除：`jrboard --uninstall-statusline`。

**現代 Debian/Ubuntu（PEP 668 擋 `pip install`）**：minimal 安裝**需先 `sudo apt install python3-venv`**（否則 `python3 -m venv` 會因缺 ensurepip 而失敗），再：
```bash
python3 -m venv ~/.jrboard && ~/.jrboard/bin/pip install tokyo-train-board
~/.jrboard/bin/python -m jrboard install-statusline     # 指令會自動指向這個 venv 的 python
```
> 不想動 `sudo` 就用上面的一鍵 bootstrap（clone 回退完全免 sudo）。

### 手動設定（或自訂指令）

在 `~/.claude/settings.json`：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 -m jrboard --mode statusline --claude-stdin --tokens --by-session --columns 80",
    "refreshInterval": 1
  }
}
```

兩個狀態列的本質限制（已在設計內處理）：

1. **非 TTY**：statusLine 指令沒有終端寬度，**必須用 `--columns N` 明確給寬度**，跑馬燈才會捲動。
2. **非計時器驅動**：Claude Code 只在 render（有活動）時才重跑指令，所以跑馬燈是「每次刷新前進一格」而非閒置時平滑流動。捲動偏移量由當前時間推導，因此每次刷新位置都不同。

`--scroll-all` 可改成整行一起捲動（連站名一起跑）。

**自適應寬度（RWD）**：內容會依 `--columns`（或主題的 `JR_COLUMNS`）的寬度預算重排，且**永不超出**：寬畫面顯示完整跑馬燈 + `5h · 7d · ctx` 額度；變窄時 token 依序遞減（先丟 `ctx`、再 `7d`、只留 `5h`），更窄則完全不顯示 token、只留電車。把 `JR_COLUMNS` 設成你的終端寬度即可（statusLine 量不到實際寬度，所以用這個數字當預算）。

### 用 csl 主題（推薦，會動的跑馬燈）

若你用 [`csl`](https://) 狀態列主題管理器，本專案附了一個現成主題（覆寫 `render()` 呼叫上面的跑馬燈，並靠 `settings.json` 的 `refreshInterval: 1` 達成**每秒前進一格的真實捲動**）。主題隨套件打包，**免手動 cp、免 clone**：

```bash
jrboard install-csl-theme            # 複製 jr-board 主題進 ~/.config/csl/themes（也可 jrboard install-csl-theme jr-timetable）
csl preview jr-board                 # 先試跑一次
csl set jr-board                     # 啟用（自動改寫 settings.json 並備份）
csl set bastille-day                 # 隨時切回原本的主題
```

> clone 安裝（沒 pip）時，改用 `python3 <clone>/main.py --install-csl-theme`，效果相同。

在 `jr-board.sh` 頂部可調 `JR_LINE` / `JR_STATION` / `JR_COLUMNS`（越窄越會捲）/ `JR_SCROLL_ALL`。

### 即時感功能：倒數、服務時間軸、額度警報、誤點/警報 overlay

讓看板「活起來」的四個旗標（皆純 stdlib，與上面所有模式組合）：

```bash
# ① 倒數：顯示「あと N 分」(每次 render 從時鐘重算 → 跑馬燈每秒在動)，取代固定 HH:MM
jrboard --mode statusline --claude-stdin --by-session --countdown --columns 80

# ② 服務時間軸：始発→終電 服務條 + now 指標 + 末班 ⚠ 警示 (收班前 90 分內)
jrboard --line oedo --station roppongi --timeline

# ③ 額度警報：Claude 5h/7d token 用量 ≥90% 時，行首亮紅「⚠速度制限 5h 92%」(只顯示真實 %)
jrboard --mode statusline --claude-stdin --show-rate-limits --columns 80

# ④ 誤點/警報 overlay：本地 alerts.json 給對應車次加 [+N分]/⚠ 徽章 + 原因頁尾 (免 ODPT key)
jrboard --line yamanote --station shinjuku --alerts ~/.config/jrboard/alerts.json
# 離線快取：把 live(ODPT) 班次寫成 JSONL，來源無資料時回放最近 30 分內的快照 (src: CACHE)
jrboard --line chuo --station tokyo --cache-dir ~/.jrboard/cache
```

`alerts.json` 格式（任何 cron/scraper 都能寫，是未來接 ODPT 即時資料的底層）：
```json
[{"line": "yamanote", "station": "shinjuku", "times": ["21:52"], "delay_min": 2, "reason": "人身事故"}]
```
> `line`/`station`/`times` 都是選用過濾條件：缺 `line`/`station` 表示不限；缺/空 `times` 表示整條線所有班次。

**GTFS-Realtime（真實即時誤點/警報）**：裝 `[gtfs]` extra 後，設 `GTFS_RT_URL` 指向業者的 GTFS-RT feed，jrboard 會把 `TripUpdate` 的誤點與 `Alert` 蓋到對應路線的班次上（`src: GTFS-RT`）。核心仍零依賴——protobuf 只在 `[gtfs]` extra、且 lazy import。
```bash
pip install "tokyo-train-board[gtfs]"
export GTFS_RT_URL="https://<operator>/gtfs-rt"   # 開關；presence 即啟用
export GTFS_RT_ROUTE_ID="odpt.Railway:JR-East.ChuoRapid"   # 選用：feed route_id 與線路對不上時覆寫
jrboard --line chuo_rapid --station tokyo
```
> 來源鏈：`GTFS-RT → ODPT → CACHE → STATIC`，誤點/警報以 overlay 方式蓋上（不偽造班次）。可接的 feed 來源見 [`docs/LIVE-DATA-APIS.md`](docs/LIVE-DATA-APIS.md)。

### Claude 感知旗標：token 量表、依 session 變化、巡迴、多行 minitable

statusLine 指令會在 STDIN 收到一份 Claude Code 的 JSON（含 `session_id`、`rate_limits`、`context_window` 等，欄位都可能缺）。加上 `--claude-stdin` 即可讀取它（不接管道也安全，會自動略過）。

- **`--tokens`** — 在結尾附上精簡的 token 量表：`5h 42% · 7d 18% · ctx 30%`。
  - `5h` = **本 session 的五小時用量**（`rate_limits.five_hour.used_percentage`）；
  - `7d` = **每週七天用量**（`rate_limits.seven_day.used_percentage`）；
  - `ctx` = 上下文視窗用量。各段依門檻上色：<70 綠、70–89 黃、≥90 紅。缺值就省略該段。
- **`--by-session`** — 從 `session_id` 以穩定雜湊決定路線：**同一個 session 永遠對到同一條線，不同 session 對到不同線**。需搭 `--claude-stdin`，可用 `--city` 縮小範圍。沒有 session id 時退回 `--rotate`，再退回設定檔預設。
- **`--rotate [MIN]`**（statusline / minitable）— 依時間分桶在（受 `--city` 限定的）路線池裡輪播，每 `MIN` 分鐘換一條（不給值＝0.5 分＝30 秒）。同一分桶內的渲染保持同一條線，跨桶就換線。`--by-session` 優先於 `--rotate`。
- **`--mode minitable`** — 多行小型站牌：第一行是站名 + token 量表，接著 2–3 行班次（`HH:MM 方面`），像月台燈號板那樣堆疊。

```bash
# token 量表 + 依 session 決定路線（限定 Tokyo），單行跑馬燈
cat cc.json | python3 main.py --mode statusline --claude-stdin --tokens --by-session --city Tokyo --columns 72
# 多行 minitable + token 量表 + 巡迴（限定 Kyoto）
cat cc.json | python3 main.py --mode minitable --claude-stdin --tokens --rotate --city Kyoto --columns 60
```

### 如何讓每個 session 顯示不同的狀態列

1. **`JR_BY_SESSION=1`（jr-board / jr-timetable 主題的預設）**：自動依 `session_id` 變化，不同 Claude session 顯示不同路線。設 `0` 可關閉。
2. **per-project `.claude/settings.json` 覆寫**：在某個專案裡放一份專屬的 `statusLine.command`（例如 `--line oedo --station tochomae` 固定一條線，或設不同的 `--city`），該專案就有專屬的狀態列。

### 兩個 csl 主題：`jr-board` vs `jr-timetable`

| 主題 | 模式 | 外觀 |
|------|------|------|
| `jr-board` | `statusline` | **單行**橫向捲動跑馬燈（站名釘左、班次捲動），尾端接 token 量表 |
| `jr-timetable` | `minitable` | **多行**小站牌：標題列（站名 + token 量表）＋ 接下來 2–3 班 |

兩者預設 `JR_BY_SESSION=1` 且 `JR_TOKENS=1`，可在各自的 `.sh` 頂部用 `JR_CITY` / `JR_ROTATE` / `JR_LINE` / `JR_STATION` / `JR_COLUMNS` 調整。

```bash
cp integrations/csl/jr-timetable.* ~/.config/csl/themes/
csl set jr-timetable     # 多行版本
```

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
