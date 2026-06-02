# 🚉 JR・東京メトロ 反転フラップ式発車案内板

[English](README.en.md) · [繁體中文](README.md) · **日本語**

[![PyPI](https://img.shields.io/pypi/v/tokyo-train-board)](https://pypi.org/project/tokyo-train-board/)
[![Python](https://img.shields.io/pypi/pyversions/tokyo-train-board)](https://pypi.org/project/tokyo-train-board/)
[![CI](https://github.com/JaeggerJose/tokyo-train-board/actions/workflows/ci.yml/badge.svg)](https://github.com/JaeggerJose/tokyo-train-board/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

JR・東京メトロの駅にある**反転フラップ式（ソラリ式）案内表示**をターミナルで再現するシミュレーターです。

```bash
pip install tokyo-train-board && jrboard
```

更新のたびに、まず昔ながらの駅・空港のフラップ板のようにランダムに回転し、その後一文字ずつ実際の次の発車情報へと確定します。20 路線対応、データ駆動設計、ODPT のリアルタイムデータにも接続でき、Claude Code のステータスラインに組み込める一行マーキー表示も備えています。

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

> 実際のターミナル出力では各路線の公式ラインカラー（山手線の黄緑、銀座線のオレンジ、丸ノ内線の赤など）で表示されます。

---

## ✨ 機能

- **本物のデータ**：[ODPT](https://www.odpt.org/)（公共交通オープンデータ）API に接続してリアルタイムの時刻表を取得。キー未設定時は内蔵の現実的な静的時刻表へ自動フォールバックします。案内板の右下にデータ源を `src: ODPT` / `src: STATIC` と正直に表示します。
- **20 路線を切り替え可能**、すべてデータ駆動（下の一覧表を参照）。
- **フラップアニメーション**：定番の反転フラップ式（ソラリ式）演出、速度調整可能。
- **一行マーキー表示**：駅名を固定し、発車情報がスクロール。Claude Code のステータスラインに組み込めます。
- **CJK 桁揃え**：`east_asian_width` で日本語の全角文字（2 セル幅）を処理し、各行を正確な表示幅に揃えます。

---

## 🚀 クイックスタート

```bash
# （任意）ODPT のライブデータ取得時のみ必要
pip install requests

# 全 20 路線と駅を一覧表示
python3 main.py --list

# 全案内板 + フラップアニメ（既定は山手線・新宿、10 秒ごとに更新。Ctrl-C で終了）
python3 main.py
```

`--station` は**英語名・駅番号・駅 id** を受け付けます（大文字小文字不問。例：`--station shinjuku`、`--station 17`、`--station JY17`）。

```bash
# 路線・駅を指定し、一度だけ描画して終了
python3 main.py --once --line ginza        --station ginza
python3 main.py --once --line keihintohoku --station tokyo --no-flap

# フラップ速度の調整
python3 main.py --line yamanote --station shinjuku --flap-delay 0.15   # ゆっくり、機械的に
python3 main.py --line yamanote --station shinjuku --flap-steps 8      # コマ数少なめ、軽快に

# 一行マーキー
python3 main.py --mode statusline --line oedo --station tochomae --columns 70
python3 main.py --mode statusline --line marunouchi --station tokyo --columns 70 --scroll-all
```

---

## 🧩 その他のモード：TUI・ポモドーロ・通勤ガーディアン・アジェンダ

案内板とステータスラインに加え、同じ CLI が 4 つの追加モードを提供します
（既存フラグの挙動は不変。これらはすべてオプトインです）。

```bash
# インタラクティブな curses ブラウザ：左に「都市ごとに分類」した路線リスト
#（各路線の公式カラー。j/k で移動、/ で絞り込み、h/l で駅送り、f でお気に入り、
# q で終了）、右にライブのカラー案内板（路線・駅の切替時にフラップ演出）
python3 main.py --tui

# ポモドーロ＝電車の旅：集中タイマーを始発から終点への乗車として描画。
# 路線上から駅を 2 つ自動選択（または --from/--to で指定）し、フラップ
# アニメの後、毎秒再描画して「とうちゃく」（到着）まで進みます。
python3 main.py --pomodoro 25 --line yamanote
python3 main.py --pomodoro 25 --line yamanote --from shinjuku --to tokyo
python3 main.py --pomodoro 1 --line yamanote --once   # 1 フレームだけ描画

# 通勤ガーディアン：「次の電車に乗るには何時に出ればいい？」設定ファイルの
# [commute] home/work が必要（下記参照）。午前 → 家→職場、午後／夜 → 職場→家。
python3 main.py --commute                       # フル案内板
python3 main.py --commute --mode statusline     # コンパクトな一行

# アジェンダフィード：ローカルの .ics ファイルを発車元（ラベル AGENDA）として
# 使用し、時刻表の代わりに次の予定を電車のように表示します。
python3 main.py --feed-ics ~/cal.ics --once
python3 main.py --feed-ics ~/cal.ics --mode statusline --columns 70
```

### 設定ファイル

設定は `~/.config/jrboard/config.toml` から読み込みます（`XDG_CONFIG_HOME` を尊重）。
ファイルが無い・壊れている場合は無視され、常に既定値が適用されます。CLI フラグは
常に設定ファイルを上書きします。

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
leave_buffer_min = 7      # 駅までの徒歩バッファ（分）
```

TUI 内で切り替えたお気に入りは `~/.config/jrboard/favorites.txt` に保存されます
（1 行につき `line_key,station_key` を 1 組）。

### インストール／エントリポイント

```bash
pip install -e .        # `jrboard` コンソールスクリプトをインストール
jrboard --list          # `python3 main.py` と同じ CLI
jrboard --tui
```

---

## 🚇 路線一覧（20 路線）

| 記号 | `--line` キー | 路線 | 駅数 | 駅の例 |
|:----:|------|------|:----:|------|
| JY | `yamanote` | 山手線（環状）| 30 | `shinjuku` |
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

> `--line shinjuku` は**都営新宿線（地下鉄）**です。JR 各線はそれぞれ独自のキー（`chuo`／`sobu` など）を持ちます。

### 🌏 ほかの都市（京都／大阪／札幌／小樽）

`--city` で都市を絞り込み：`python3 main.py --list --city Osaka`。`--rotate --city Osaka` は大阪のみを巡回します。

| key | 都市 | 路線 | 駅数 |
|------|:----:|------|:----:|
| `osaka-loop` | 大阪 | JR 大阪環状線（環状）| 19 |
| `osaka-midosuji` | 大阪 | 御堂筋線 | 20 |
| `osaka-tanimachi` | 大阪 | 谷町線 | 26 |
| `kyoto-karasuma` | 京都 | 地下鉄烏丸線 | 15 |
| `kyoto-tozai` | 京都 | 地下鉄東西線 | 17 |
| `kyoto-randen` | 京都 | 嵐電 嵐山本線（路面電車）| 13 |
| `kyoto-sagano` | 京都 | JR嵯峨野線（山陰本線）| 15 |
| `kyoto-keihan` | 京都 | 京阪本線 | 42 |
| `sapporo-namboku` | 札幌 | 南北線 | 16 |
| `sapporo-tozai` | 札幌 | 東西線 | 19 |
| `sapporo-toho` | 札幌 | 東豊線 | 14 |
| `otaru-hakodate` | 小樽 | JR 函館本線（小樽—札幌）| 15 |

---

## 🛰️ ODPT のライブデータ

1. <https://developer.odpt.org/> で無料のコンシューマーキーを取得します。
2. 環境変数を設定して実行します：

```bash
export ODPT_KEY="あなたのキー"
python3 main.py --line yamanote --station shinjuku   # 案内板に src: ODPT と表示
```

取得に失敗した場合（キーなし・HTTP エラー・空応答）は静的時刻表へフォールバックし、理由を stderr に記録して `src: STATIC` を表示します。

> 🔐 キーをソースに直書きしたりコミットしたりしないでください。環境変数を使います（`.env` は gitignore 済み）。

---

## 📟 Claude Code のステータスラインに組み込む

複数行の案内板はステータスライン**には不向き**です（16 行を占有します）。一行 `statusline` モードを使ってください。駅名を左に固定し、発車情報を電光掲示板のように流します：

```text
[JY] 17 新宿 ▸ 15:45 品川・渋谷方面  15:45 上野・池袋方面  15:50 …
```

`~/.claude/settings.json` に：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /path/to/tokyo-train-board/main.py --mode statusline --line yamanote --station shinjuku --columns 80"
  }
}
```

ステータスライン固有の 2 つの制約（いずれも設計上で対処済み）：

1. **TTY なし**：statusLine コマンドにはターミナル幅が渡らないため、マーキーをスクロールさせるには **`--columns N` で幅を明示**する必要があります。
2. **タイマー駆動ではない**：Claude Code は描画時（操作があったとき）にのみコマンドを再実行するため、マーキーは「更新ごとに 1 桁進む」形になり、待機中になめらかに流れるわけではありません。スクロール位置は現在時刻から算出されるため、更新のたびに位置が変わります。

`--scroll-all` で行全体（駅名も含めて）をスクロールできます。

### csl テーマを使う（推奨。流れるマーキー）

[`csl`](https://) ステータスラインテーマ管理ツールを使っている場合、本プロジェクトには `integrations/csl/jr-board.sh`（＋マニフェスト）が同梱されています。`render()` を上書きして上記のマーキーを呼び出し、`settings.json` の `refreshInterval: 1` によって**実際に約 1 桁／秒でスクロール**します：

```bash
# ユーザー層へテーマを入れて有効化
cp integrations/csl/jr-board.* ~/.config/csl/themes/
csl preview jr-board     # まず一度試す
csl set jr-board         # 有効化（settings.json を書き換え、自動バックアップ）
csl set bastille-day     # いつでも元のテーマに戻せる
```

`jr-board.sh` 冒頭の `JR_LINE` / `JR_STATION` / `JR_COLUMNS`（狭いほどよくスクロール）/ `JR_SCROLL_ALL` で調整できます。

### Claude 連携フラグ：トークンゲージ・セッション別・ローテーション・複数行 minitable

statusLine コマンドは STDIN で Claude Code の JSON（`session_id`、`rate_limits`、`context_window` など。各フィールドは欠落しうる）を受け取ります。`--claude-stdin` を付けるとそれを読み取ります（パイプが無くても安全に無視されます）。

- **`--tokens`** — 末尾にコンパクトなトークン量ゲージを付加：`5h 42% · 7d 18% · ctx 30%`。
  - `5h` = **セッション（5 時間）上限**（`rate_limits.five_hour.used_percentage`）；
  - `7d` = **週次（7 日）上限**（`rate_limits.seven_day.used_percentage`）；
  - `ctx` = コンテキストウィンドウの使用率。各セグメントは閾値で色分け：<70 緑、70–89 黄、≥90 赤。値が無ければそのセグメントは省略。
- **`--by-session`** — 安定ハッシュで `session_id` から路線を決定：**同じセッションは常に同じ路線、異なるセッションは異なる路線**になります。`--claude-stdin` が必要で、`--city` で範囲を絞れます。session id が無い場合は `--rotate`、次に設定の既定値にフォールバック。
- **`--rotate [MIN]`**（statusline / minitable）— （`--city` で絞った）路線プールを時間バケットでローテーション。`MIN` 分ごとに進む（値なし＝0.5 分＝30 秒）。同一バケット内は同じ路線、バケットをまたぐと切り替わります。`--by-session` が `--rotate` より優先。
- **`--mode minitable`** — 複数行のミニ発車標：1 行目は駅名＋トークンゲージ、続けて 2〜3 件の発車（`HH:MM 方面`）を、実際のホーム発車標のように積み重ねます。

```bash
# トークンゲージ + セッション別路線（Tokyo に限定）、単一行マーキー
cat cc.json | python3 main.py --mode statusline --claude-stdin --tokens --by-session --city Tokyo --columns 72
# 複数行 minitable + トークンゲージ + ローテーション（Kyoto に限定）
cat cc.json | python3 main.py --mode minitable --claude-stdin --tokens --rotate --city Kyoto --columns 60
```

### セッションごとにステータスラインを変える方法

1. **`JR_BY_SESSION=1`（`jr-board` / `jr-timetable` テーマの既定）**：`session_id` で自動的に変化し、異なる Claude セッションは異なる路線を表示。`0` で無効化。
2. **プロジェクト単位の `.claude/settings.json` 上書き**：あるリポジトリにそのプロジェクト専用の `statusLine.command` を置く（例：`--line oedo --station tochomae` で固定、または別の `--city`）と、そのプロジェクト専用のステータスラインになります。

### 2 つの csl テーマ：`jr-board` と `jr-timetable`

| テーマ | モード | 見た目 |
|--------|--------|--------|
| `jr-board` | `statusline` | **単一行**の横スクロールマーキー（駅名を左に固定、発車をスクロール）＋右端にトークンゲージ |
| `jr-timetable` | `minitable` | **複数行**のミニ発車標：ヘッダ行（駅名＋トークンゲージ）＋次の 2〜3 本 |

どちらも既定で `JR_BY_SESSION=1` と `JR_TOKENS=1`。各 `.sh` 冒頭の `JR_CITY` / `JR_ROTATE` / `JR_LINE` / `JR_STATION` / `JR_COLUMNS` で調整できます。

```bash
cp integrations/csl/jr-timetable.* ~/.config/csl/themes/
csl set jr-timetable     # 複数行版
```

---

## 🎞️ フラップアニメーションの調整

| フラグ | 既定 | 効果 |
|------|:----:|------|
| `--no-flap` | — | アニメを省略し、確定後の案内板を描画 |
| `--flap-steps N` | 22 | 全ランダムから確定までのコマ数。大きいほど段階的 |
| `--flap-delay S` | 0.08 | 1 コマあたりの表示秒数。大きいほど遅い |

既定のアニメーションは約 2 秒です。文字が確定する**順序**は `jrboard/flap.py` の `lock_threshold()` が決めています（現在は左から右へのワイプ＋わずかなジッター）。ランダム確定や ease-out にしたい場合はこの関数だけを変えれば、他のモジュールには触れずに済みます。

---

## 🏗️ アーキテクチャ

**データ駆動**：エンジンは路線非依存で、**路線の追加 = `jrboard/data/<key>.json` を 1 つ置くだけ。コード変更は不要**です。

| モジュール | 役割 |
|------|------|
| `jrboard/width.py` | CJK / ANSI の表示幅計算と桁揃え |
| `jrboard/model.py` | `Line` / `Station` データモデル、`data/*.json` を読み込み |
| `jrboard/sources.py` | 時刻表ソース（ODPT + 静的フォールバック、リポジトリパターン）|
| `jrboard/flap.py` | 反転フラップアニメーションエンジン（純粋関数・テスト可能）|
| `jrboard/render.py` | 案内板の ANSI 描画 |
| `jrboard/statusline.py` | 一行マーキー |
| `jrboard/cli.py` | argparse CLI と更新スケジューリング |
| `jrboard/data/*.json` | 路線ごとの駅・時刻表データ |

### 路線を追加する

既存ファイルと同じ構造で `jrboard/data/` に `<key>.json` を置きます：

```jsonc
{
  "key": "tokaido",
  "name_jp": "東海道線", "name_en": "Tokaido Line",
  "symbol": "JT",
  "color": { "name": "...", "ansi_fg": "[38;2;246;139;30m",
             "ansi_bg": "[48;2;246;139;30m[38;2;26;26;26m", "hex": "#F68B1E" },
  "operator": "JR-East",
  "odpt_railway": "odpt.Railway:JR-East.Tokaido",
  "loop": false,
  "stations": [
    { "id": "JT01", "number": "01", "name_jp": "東京", "kana": "とうきょう",
      "name_en": "Tokyo", "odpt_station": "odpt.Station:JR-East.Tokaido.Tokyo" }
  ],
  "timetable": {
    "first_train": "04:30", "last_train": "00:30",
    "headway_min": { "weekday": { "7": 5, "8": 4 }, "holiday": {} },
    "directions": [
      { "id": "down", "name_jp": "熱海方面", "via_jp": "横浜方面", "track": "1" },
      { "id": "up",   "name_jp": "東京方面", "via_jp": "品川方面", "track": "2" }
    ]
  }
}
```

ラインカラーは公式 hex から `scripts/apply_colors.py` で再生成できます（24-bit トゥルーカラー + 輝度による記号文字色の自動選択）。

保存後、`python3 main.py --list` にすぐ新しい路線が現れます。

---

## ✅ テスト

```bash
python3 -m pytest tests -q      # 50 tests
```

カバー範囲：表示幅（CJK + ANSI）、データモデル（読み込み・駅検索・環状の隣接駅）、時刻表ソース（静的生成と ODPT→静的フォールバック）、フラップ（幅保持・最終コマで完全確定）、ステータスライン（駅名固定・時刻で進むマーキー・ラインカラー）。
