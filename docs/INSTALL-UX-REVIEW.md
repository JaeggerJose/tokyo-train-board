# 安裝體驗審查：csl + JR-timetable theme

> 實測日期：2026-06-02 · 測試機：`mike@10.6.0.4`（Ubuntu 24.04、Python 3.12.3、minimal）
> 方法：在乾淨的 Ubuntu 24.04 上模擬「全新使用者」走完文件流程，記錄每個摩擦點。所有結論都有實測輸出佐證（非破壞性，temp 目錄、裝完即清）。

---

## 1. 現況：兩條安裝鏈怎麼運作

### A. `csl`（Claude Status Line 管理器）
`csl` 是 `~/.claude/statusline/bin/csl` 的 bash 腳本，symlink 到 `~/.local/bin/csl`。

| 路徑 | 步驟 | 硬依賴 |
|------|------|--------|
| 外掛 | `/plugin install csl@claude-statusline` → `/csl:setup` | `jq`、bash、`~/.local/bin` 在 PATH |
| git clone | `git clone …/claude-statusline ~/.claude/statusline && ./install.sh` | 同上 |

`csl set <theme>` 會改寫 `~/.claude/settings.json` 的 `statusLine.command`（自動備份 `.csl.bak`）。

### B. JR-timetable theme（本專案）— 兩條子路徑
1. **一鍵 statusLine（免 csl）**：`pip install tokyo-train-board` → `jrboard install-statusline`
   - 指令用 `<python> -m jrboard` 產生，所以**即使 `jrboard` 不在 PATH 也能跑**（設計良好）。
   - Ubuntu 文件建議改走 venv：`python3 -m venv ~/.jrboard && ~/.jrboard/bin/pip install …`
2. **csl theme**：`pip install tokyo-train-board` + `cp integrations/csl/jr-board.* ~/.config/csl/themes/` + `csl set jr-board`
   - repo 內 theme 已 **portable**（`python -m jrboard`，`JR_HOME` 留空即用 pip 套件；設了才用 clone）。

關鍵事實：**`tokyo-train-board` 的 `dependencies = []`（零依賴）**，且套件已上 PyPI（HTTP 200）。

---

## 2. 在 mike@10.6.0.4 的實測結果

### 環境探測
| 依賴 | 狀態 | 影響 |
|------|------|------|
| `python3` 3.12.3 | ✓ | — |
| `jq` / `git` / `curl` | ✓ | **csl 的硬依賴 jq 預設就在** |
| `pip3` | ✗ | pip 路徑全卡 |
| `pipx` | ✗ | pipx 路徑全卡 |
| `python3 -m venv` | ⚠️ 模組在但**缺 ensurepip** | venv 造不出 pip |
| PEP 668 `EXTERNALLY-MANAGED` | 存在 | 系統 pip 被鎖 |
| `node` / `npm` / `claude` | ✗ | 該機沒有 Claude Code 本體 |
| `~/.local/bin` 在 PATH | ✗ | console script／csl symlink 不被找到 |
| 免密 sudo | ✗ | 無法無人值守 apt |

### 各安裝路徑測試
| 路徑 | 結果 | 證據 |
|------|------|------|
| `pip install tokyo-train-board` | ❌ | 無 pip + PEP 668 鎖死 |
| `python3 -m venv`（文件主推的「免 sudo」路徑） | ❌ | `ensurepip is not available … apt install python3.12-venv` |
| `pipx install` | ❌ | 無 pipx，需 `sudo apt install pipx` |
| **git clone + `python3 main.py`（零安裝）** | ✅ | 成功渲染彩色翻牌（札幌 08 大通線）+ 多行山手線看板，**全程無 pip/venv/sudo** |

### 致命結論
> 在 minimal Ubuntu 24.04 上，**文件列出的每一條 pip/venv/pipx 路徑都需要先 `sudo apt`**。
> 文件把 venv 寫成「免 sudo」，但實機因缺 `python3.12-venv` 而失敗 —— 描述與現實不符。
> **唯一不需 sudo 的可行路徑（git clone 直跑）反而沒被當主推。** 這就是「不 user-friendly」的根因。

---

## 3. user-friendly 評分

| 對象 | 在這台機 | 評語 |
|------|----------|------|
| **csl** | 🟡 中 | `jq` 預設在 → 只差 `git clone + install.sh`，但 `~/.local/bin` 不在 PATH 要手動修；且需先有 Claude Code 本體 |
| **JR-timetable（pip 路徑）** | 🔴 差 | 三條官方路徑全要 sudo apt，新手會直接卡死 |
| **JR-timetable（clone 直跑）** | 🟢 好 | 零依賴的優勢完全沒被行銷出來 |

---

## 4. 簡化建議（你要的「像 pip/apt 自動裝依賴」）

### 🥇 P0 — 一行 bootstrap，自動偵測管道、零依賴必勝回退
利用「零依賴」這個最大槓桿：**任何有 `python3` 的機器都能跑，不需 pip/venv/sudo**。

```bash
curl -fsSL https://raw.githubusercontent.com/JaeggerJose/tokyo-train-board/main/install.sh | bash
```

`install.sh` 邏輯（依序嘗試，第一個成功就停）：
1. 找 `python3`（>=3.11）。沒有才提示裝 python（這是唯一真正必要的系統依賴）。
2. 試 `pip install --user tokyo-train-board`（quiet）。
3. 試 `pipx install tokyo-train-board`。
4. **必勝回退**：`git clone --depth 1` 到 `~/.local/share/jrboard`，在 `~/.local/bin/jrboard` 放一個 launcher：`exec python3 ~/.local/share/jrboard/main.py "$@"`。
5. 跑 `jrboard install-statusline`（已用 `python -m jrboard`，PATH 無關 → 直接寫進 `settings.json`）。
6. PATH 自檢：`~/.local/bin` 不在 PATH 就 append 到 `~/.bashrc`/`~/.zshrc`（或印出確切該加的行）。

### 🥈 P1 — 把 csl theme 安裝收進子指令，免手動 cp、免 clone
新增 `jrboard install-csl-theme`：把 portable theme 從 **package-data** 複製進 `~/.config/csl/themes/`，然後提示 `csl set jr-board`。
（`pyproject.toml` 已有 `package-data`，把 `integrations/csl/*.sh,*.json` 一起打包即可。）

### 🥉 P2 — 文件修正（描述對齊現實）
- 把「git clone 直跑」升為 **Ubuntu/Debian 的首選**，標明「零依賴、免 sudo、免 pip」。
- venv 段落改寫：明說 minimal Ubuntu 24.04 需先 `sudo apt install python3.12-venv`，不要稱它「免 sudo」。
- 對完全鎖死的機器，提供 `pip install --user --break-system-packages` 作為明列的逃生口。

### 🔧 P3 — 順手修掉的本地 bug
本機 `~/.config/csl/themes/jr-board.sh` 是**舊版（硬編碼 `/Users/minghsuan/Downloads/JR-timetable`）**，與 repo 內 portable 版不同步。
修：`cp integrations/csl/jr-board.* ~/.config/csl/themes/`（驗證過 repo 版才是 portable 的）。

---

## 附：可選的進階打包
- **zipapp 單檔**：因零依賴，可 `python3 -m zipapp jrboard -o jrboard.pyz`，使用者 `curl -o ~/.local/bin/jrboard …pyz && chmod +x` 即得單檔可執行檔。
- **csl theme registry**：若 csl 支援遠端 theme 來源，做成 `csl install jr-board` 從 registry 拉，最接近 `apt install` 的體感。
