# jrboard 功能藍圖（multi-agent 發想綜合）

> 產出方式：7 個產品視角 agent 平行發想（live-data / aesthetics / claude-power / productivity / whimsy / ecosystem / distribution）共 **56 個原始點子**，再由 1 個綜合 agent 去重、分群、評分。日期 2026-06-06。

## 北極星
> **split-flap 翻牌隱喻就是 jrboard 的護城河。** 下一階段該讓看板「活起來」（每秒有動靜、即時誤點），並加倍押注 Claude Code 整合——**不要**去碰音效、Web、PNG 匯出那些會破壞「零依賴、終端優先」本質的東西。

---

## 🚩 Headliners（建議優先做的 4 個）

### 1. Countdown Mode（あと N 分）— 解決「看起來凍住了」
**effort: S** · 建在 `sources.py` Departure + `render.py`/`statusline.py`，**無需改 JSON**

把固定的 `15:45` 換成每次 render 從 `datetime.now()` 重算的 `あと 3 分`。這一個改動直接解掉最高頻抱怨（statusline 看起來不會動）——因為現在每秒都有東西在變。純 stdlib，與所有模式組合，把抽象時刻表變成切身的急迫感。被 **4 個視角**獨立點名為最高頻需求，也是讓誤點/末班/journey 都更好讀的前置。

```
$ jrboard --line yamanote --station shinjuku --countdown
$ jrboard statusline --line ginza --countdown   # Claude statusLine 每秒前進

  ┌─ 山手線 SHINJUKU  新宿 ────────────────────┐
  │  あと  1 分   普通    渋谷・品川方面   3番線 │  ← 紅、脈動
  │  あと  4 分   普通    渋谷・品川方面   3番線 │
  │  あと 11 分   快速    池袋・新宿方面   4番線 │
  └────────────────────────  15:42:07 ─────────┘

statusline：🚃 JY 山手 ▸ あと2分 渋谷ゆき ▸ 次 あと6分
```

### 2. Live Service Layer：誤點 + 警報 + 離線快取（ODPT，一個內聚功能）
**effort: M** · `sources.py` ODPTSource + `[live]` extra（requests 已在）+ 純 stdlib JSONL 快取

把散落的 live-data 點子併成**一層**：設了 `ODPT_KEY` 就抓誤點/警報、給受影響的車次加 `[+2分]`/`⚠️` 徽章、把停駛原因當頁尾跑馬燈，**並**把每次回應快取成 JSONL，這樣在不穩的車上 wifi 也不會空白。`src:` 徽章誠實標示每個數字的來源。這是 README 自己標的頭號 TODO——「玩具 vs 工具」的分界線。

```
$ export ODPT_KEY=...
$ jrboard --line chuo --station tokyo --cache-dir ~/.jrboard/cache

  ┌─ 中央線快速 TOKYO  東京 ──────────────────────┐
  │  15:45 [+2分] 快速   高尾方面          1番線  │  ← 琥珀徽章
  │  15:58 [遅延] 特急   松本方面          3番線  │  ← 紅、抖動
  ├────────────────────────────────────────────┤
  │ ⚠ 人身事故・運転見合わせ（八王子〜高尾）      │  ← 捲動原因
  └──────────  src: ODPT  ·  cache 14:30 ────────┘

離線時：整塊看板轉暗灰，標 src: CACHE (28分前)
```
> 來源鏈：ODPT → CACHE(<30m, 變暗) → static。`Departure` 加 nullable 欄位 `delay_sec / status / cause`。

### 3. Rate-Limit Alert Train（Claude 原生戲劇性）
**effort: M** · `claude_input.py` 既有百分比解析 + render 時注入合成 Departure

當 Claude 的 5h/7d token 餘量低於門檻，往看板注入一列短暫的全紅閃爍「警報車」：`速度制限 — あと 18 分到着`。Solari 隱喻讓一個看不見的 API 限制突然變得具體又戲劇化。**這是整批裡最獨特、最 jrboard、最會被截圖分享的點子**——而且它只可能存在於 Claude Code 生態裡（已經在解析 token 量表）。預設關閉（`--show-rate-limits`）。

```
$ jrboard statusline --claude-stdin --show-rate-limits

  │ ▓▓ 速度制限 ▓▓  あと 18 分到着   5h session   │  ← 閃爍/紅
  │  15:45  普通   渋谷方面                3番線  │

statusline：⚠ 速度制限 あと18分 ▸ JY 渋谷ゆき あと2分
```

### 4. Last-Train Alert + 24h 服務時間軸
**effort: S** · `model.py` Line.first_train/last_train + 既有時間解析

距末班 90 分內，給最後幾班加 `⚠`；`--timeline` 畫一條全天 ASCII sparkline：綠色服務區塊、車次刻度、now 指標、收班邊緣。用近乎零的成本回答「我深夜還能不能繼續工作？」的真實恐懼，與 Countdown 天然搭配。

```
$ jrboard --line oedo --station roppongi --timeline

  大江戸線 ROPPONGI  六本木
  始発 05:11 ┤████████████████████████████┤ 終電 00:18
            05      10      15      20    ▲now 23:41
  次の電車:  23:48  普通  光が丘方面    ⚠ 終電まで あと2本
  終電:      00:18  普通  光が丘方面    ⚠
```

---

## ⚡ Quick Wins（S effort，建議順手做）
- **`--minimal` 靜默計時渲染**：站名 + countdown + 月台，無框無色（尊重 `--no-color`）。純 render 重構，給專注模式與乾淨的 statusline 回退。
- **每線 flap 緩動曲線**：把 `flap.py` 的 `lock_threshold()` 一般化成一組純函式（linear/bounce/ease-out），用 JSON `flap_easing` 欄位選。山手線俐落、大江戸線重力感——純數學、可測、零依賴、每線有個性。
- **依時段日/夜配色**：stdlib `datetime`（+ 選用 `$COLORFGBG`）切換夜間柔和 / 日間鮮明，用選用 JSON `day_ansi`/`night_ansi`。Claude 24/7 跑，夜間護眼。
- **電車蒐集連續打卡 streak**：`~/.config/jrboard/streak.json` 記連續天數搭不同線，statusline 顯示 `[Streak: 7⚡]`。Duolingo 式習慣迴路。
- **車站心情點綴（emoji/kanji）**：選用 `mood_emoji`（秋葉原→🎮電子、浅草→⛩️参拝）當頁尾點綴。純資料層，適合詼諧的調性、易截圖。
- **本地 `alerts.json` watcher**：`os.stat` 輪詢 `~/.config/jrboard/alerts.json` 給匹配車次加徽章。不靠 ODPT 硬依賴就有 live 警報的爽度——任何 cron/scraper 都能餵；之後變成 ODPT 層寫入的底層。

## 🎯 Bigger Bets（M/L，之後做）
- **站到站行程規劃 `--journey from=… to=…`**：用既有 `odpt_station` id 走圖、串接 + 轉乘，每段疊一個看板。stdlib-only，免 API（靜態班距回退）。延伸 `journey.py`。
- **每專案決定性線路對映**：Claude Code workspace/repo → 固定線路（`.claude` 設定），讓某專案永遠閃「它的」顏色形成肌肉記憶。與 rate-limit train 合成一個 Claude 原生儀表板。
- **Session 里程碑 journey `--milestones`**：把長 session 變成 journey，context-% 門檻與任務完成是虛擬車站，進度條是車的位置。Countdown 落地後做動感才好。
- **來源鏈加 GTFS-RT 回退**：在 ODPT 與 cache 之間加一層，補 ODPT 沒覆蓋的線。等 ODPT live 層 + cache 存在後再做。
- **Plugin hooks + line-pack registry**：`importlib` 載入 `~/.config/jrboard/plugins.py` 的 `on_departure`/`on_render` + git-based `install-pack nyc-subway`。把資料驅動架構變成生態，把非日本覆蓋外包給貢獻者——但要在核心 live data 穩了之後，否則只是空平台。

## 🌙 Moonshots（有野心/有風險但興奮）
- **Agent fleet 月台看板**：把平行的 Claude subagent 渲染成同時發車的車次（每條虛擬線顯示 cost/tokens/完成%，到站=完成），payload 從 STDIN 來。最有野心的隱喻表達，但需要一個尚不存在的穩定 agent-status feed。
- **可嵌入的零依賴 Web demo**（flap/render 的 JS 移植）：手移約 500 行到 vanilla JS，做點即玩的 GitHub Pages demo。巨大的曝光/轉換槓桿（零安裝阻力），但會把渲染邏輯分叉成第二語言要維護——只在 Web 曝光變成真實成長目標時做。
- **asciinema 螢幕錄製 `--record`**：用 stdlib `pty` 把 session 錄成 `.cast`，比 GIF 更適合 CLI 展示且可存檔。在本質內（cast 是 JSON、pty 是 stdlib），但是發行工具不是產品功能——低優先。

## ✂️ Cut（刻意不做，保持產品鋒利）
- **車站發車音樂 / lo-fi 環境音 / 發車鈴（所有音效模式）**：音效破壞終端優先、零依賴本質（要 ffplay/afplay、要打包媒體、跨平台靜默失敗、在 statusline 裡無用）。詼諧但離調，果斷砍。
- **PNG / 社群卡 / 動態 GIF / SVG 匯出**：拉進 Pillow 或外呼 ffmpeg/imagemagick——為行銷產物背一大包選用依賴。`demo.gif` 已存在做推廣。真要匯出，只接受 stdlib 字串做的 ANSI→HTML/SVG。
- **SQLite 有狀態 session 庫 + history API**：對需求過度設計。streak/favorites 幾 KB JSON 就夠；SQLite schema + history/bookmarks API 是往「交通伴侶 DB」的範圍蔓延，還複雜化鎖死機器的安裝故事。用扁平 JSON。
- **Email digest / SendGrid / GitHub Actions cron 伴侶**：email 投遞、API key、CI 排程是完全不同的產品面，高維護、離平台、增加密鑰管理負擔。出界。
- **可匯入 widget library + Flask 範例**：過早平台化。穩定+文件化一個公開 render API 是維護稅，在有第三方需求前就綁住內部重構。等真有整合者再說。
- **通勤路徑最佳化（Dijkstra 多線）+ 天氣配色 API**：路徑最佳化是 L-effort 路由引擎、和 Google Maps 競爭、遠超看板本分；行程規劃已覆蓋 80%。天氣配色為純裝飾加網路依賴——用 stdlib 的季節日期配色就能抓到那個味道。
