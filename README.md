# JR / Tokyo Metro Split-Flap Board

終端機裡的 JR / 東京地鐵 **翻牌式（split-flap / Solari board）時刻表站牌**模擬器。
每次刷新會先像老火車站／航站樓那樣亂數翻滾，再逐格鎖定成真實資訊。

![sample](Screenshot%202026-05-31%20at%201.48.13%20PM.png)

## 功能

- **真實資料**：可接 [ODPT](https://www.odpt.org/)（公共交通開放資料平台）即時時刻表；
  未設定金鑰時自動回退到內建的真實靜態時刻表（站牌底部標示 `src: ODPT` / `src: STATIC`）。
- **14 條路線可切換**：JR 山手線 + 東京 Metro 9 條 + 都營地下鐵 4 條，全部資料驅動。
- **翻牌動畫**：split-flap 翻牌效果（`jrboard/flap.py`）。
- **單行跑馬燈模式**：可接 Claude Code statusLine（站名釘住、班次捲動）。

## 安裝

```bash
pip install requests            # 只有接 ODPT 時需要；靜態備援不需要
```

## 用法

```bash
# 列出全部路線與站點
python3 main.py --list

# 全站牌 + 翻牌動畫（預設山手線新宿，每 10 秒刷新）
python3 main.py

# 指定路線 / 站點，渲染一次就結束
python3 main.py --once --line ginza --station ginza
python3 main.py --once --line oedo  --station tochomae --no-flap

# 單行跑馬燈
python3 main.py --mode statusline --line yamanote --station shinjuku
python3 main.py --mode statusline --line oedo --station tochomae --columns 60
python3 main.py --mode statusline --line marunouchi --station tokyo --scroll-all
```

`--station` 接受英文名、站號或 id（大小寫不拘）。

### 接 ODPT 即時資料

到 <https://developer.odpt.org/> 免費申請 consumer key，然後：

```bash
export ODPT_KEY="你的金鑰"
python3 main.py --line yamanote --station shinjuku   # 站牌會顯示 src: ODPT
```

金鑰不要寫進程式或 commit；用環境變數即可（`.env` 已被 gitignore）。

## 接進 Claude Code statusLine

多行站牌**不適合** statusLine（會佔 16 行）。請用單行 `statusline` 模式。

在 `~/.claude/settings.json`：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/minghsuan/Downloads/JR-timetable/main.py --mode statusline --line yamanote --station shinjuku --columns 80"
  }
}
```

兩個 statusLine 的本質限制（已在設計內處理）：

1. **非 tty**：statusLine 指令沒有終端寬度，所以必須用 `--columns N` 明確給寬度，跑馬燈才會生效。
2. **非計時器**：Claude Code 只在 render（有活動）時重跑指令，所以跑馬燈是「每次刷新前進」而非閒置時平滑流動。偏移量由當前時間推導，因此每次刷新位置都不同。

## 架構

資料驅動：引擎與路線無關，**新增路線 = 在 `jrboard/data/` 丟一個 `<key>.json`**，不必改任何程式。

| 模組 | 職責 |
|------|------|
| `jrboard/width.py` | CJK 全形字 / ANSI 視覺寬度計算與對齊 |
| `jrboard/model.py` | `Line` / `Station` 資料模型，載入 `data/*.json` |
| `jrboard/sources.py` | 時刻表來源（ODPT + 靜態備援，repository pattern）|
| `jrboard/flap.py` | split-flap 翻牌動畫引擎（純函式、可測）|
| `jrboard/render.py` | 站牌 + 時刻表 ANSI 渲染 |
| `jrboard/statusline.py` | 單行跑馬燈 |
| `jrboard/cli.py` | argparse CLI 與排程 |

```bash
python3 -m pytest tests -q     # 47 tests
```
