# jrboard data integrity & honesty audit

- Snapshot of `main` @ 8e01d57 (2026-11-19). File:line references point at that commit; later fixes may have moved them.
- Read-only audit. The helper scripts it mentions (structural validator, sibling cross-check, holiday-rule check, Toei GTFS first/last extraction) were throwaway and are not in the repo.
- Fixes are tracked in follow-up PRs; this document is not updated as they land.

> STATUS: complete (2026-11-19). Confirmed errors (§B.4) are kept separate from suspected ones (§B.5).

---

## A. Honesty audit

### A.0 What the code actually does (verified by reading + running)

| Behaviour | Evidence |
|---|---|
| Default (no `ODPT_KEY`) departures are **synthesized**: a headway grid from `timetable.headway_min[weekday/holiday][hour]`, shifted +1 min per station index. No real timetable exists anywhere in the package. | `jrboard/sources.py:136-244` (`StaticSource`), `_station_phase` at :123 |
| `StaticSource` **ignores `first_train` / `last_train`**. Hours missing from `headway_min` or set to `0` fall back to `_DEFAULT_GAP = 5`, so the board shows a train every 5 min all night. | `sources.py:238-244`. Ran it: `ginza` @ 渋谷, Thu 03:00 → `03:00 上野方面, 03:00 銀座方面, 03:05 …`; `shinkansen-tokaido` @ 東京, 01:30 → `01:30 新大阪方面, 01:30 東京方面, 01:35 …` |
| At a terminus the board lists departures **toward that terminus** (e.g. 東京 on the Tōkaidō Shinkansen shows `東京方面`; 渋谷 on Ginza shows `銀座方面` for the Shibuya-bound direction). | same run as above; `_direction_departures` never checks station position |
| Day type = `now.weekday() >= 5`; Japanese national holidays use weekday headways. The ODPT path has the same bug (`odpt:calendar` = `Weekday` on holidays). | `sources.py:118-120`, `:272-276`. Run on Mon 2026-11-23 (勤労感謝の日) used weekday table (`kyoto-randen` 12:03/12:13 = weekday 10-min headway) |
| Board footer shows `src: <label>`; **statusline, minitable and `--timeline` discard the label** (`departures, _label = …`). The modes embedded in Claude Code therefore never disclose provenance. | `cli.py:650`, `cli.py:825`; board: `render.py:284`; TUI: `tui.py:482-483` |
| `--cache-dir` replay only fires when `departures` is empty, but `get_departures` falls back to `StaticSource` on any ODPT failure, which is never empty for a line with directions. So after an ODPT outage you get synthesized `STATIC` rows, **not** the cached real snapshot. The cache is effectively dead code. | `cli.py:528-537` + `sources.py:421-431` |
| Cached rows are replayed **unfiltered**: a 25-min-old snapshot can show trains that already left. The age is shown (`CACHE (N分前)`), which is honest. | `cache.py:55-102`, `cli.py:534-537` |
| GTFS-RT overlay stamps the **max delay of any trip on the route onto every row**, and any alert with no `informed_entity.route_id` onto every line. If at least one row is stamped, the label becomes `GTFS-RT` **even when the base rows were synthesized by `StaticSource`**. | `gtfs_rt.py` `decode_feed` / `overlay`; `sources.py:433-438` |
| Default GTFS-RT route key is `line.odpt_railway` (e.g. `odpt.Railway:JR-East.ChuoRapid`), which is not a GTFS `route_id` in any operator feed. Without `GTFS_RT_ROUTE_ID` nothing matches. | `gtfs_rt.py` `overlay()` |
| ODPT path drops departures whose HH:MM is numerically < now (`slot < now_min`), so at 23:50 the 00:05 train disappears; it also sorts by plain minutes-since-midnight. (Code-read; not run against the live API.) | `sources.py:337`, `:309` |

### A.1 Inventory of user-facing claims

| # | Where | Claim (verbatim, abridged) | Verdict |
|---|---|---|---|
| 1 | `README.md:16` | 「再逐格鎖定成**真實的到站資訊**」 | **Inaccurate** in the default mode (synthesized). |
| 1 | `README.en.md:16` | "locks … into **the real upcoming departures**" | **Inaccurate** (same). |
| 1 | `README.ja.md:16` | 「**実際の次の発車情報**へと確定」 | **Inaccurate** (same). |
| 2 | `README.md:17`, `.en:16`, `.ja:16` | 「可接 ODPT **即時**資料」 / "optional **live** ODPT data" / 「ODPT の**リアルタイム**データ」 | **Misleading.** What the code fetches is ODPT `StationTimetable`, the published *schedule*, not real-time positions/delays; and only for operators that publish it on ODPT (see D). |
| 3 | `README.md:46` | 「**真實資料**：…即時時刻表；未設定金鑰時自動回退到內建的**真實靜態時刻表**。站牌右下角誠實標示…」 | **Inaccurate ×3**: no real static timetable exists (synthesized); ODPT ≠ live; the label is not shown in statusline/minitable/timeline. |
| 3 | `README.en.md:45` | "**Real data** … live timetables; falls back to a built-in **realistic static timetable** … honestly labels its source" | **Inaccurate** (heading "Real data", "live", label only in board/TUI). "realistic" is softer than zh-TW 真實 but still implies a timetable. |
| 3 | `README.ja.md:45` | 「**本物のデータ**…リアルタイムの時刻表…内蔵の**現実的な静的時刻表**…正直に表示」 | **Inaccurate** (same as en). |
| 4 | `README.en.md:46` | "**20 switchable lines**" | **Stale** (50 lines). |
| 5 | `README.md:200`, `.en:204`, `.ja:203` | 「未接即時資料時，時刻依班距推算，站間時間固定以每站 1 分鐘估算，和實際行車時間有落差」 | **Accurate and honest** — but buried in the Shinkansen subsection although it applies to all 50 lines. |
| 6 | `README.md:227`, `.en:231`, `.ja:230` | ODPT failure → "falls back to the **static timetable** … shows `src: STATIC`" | Mechanically accurate; wording "timetable" overstates. |
| 7 | `README.md:325`; `cli.py:292-294` (`--cache-dir` help) | "replay the freshest snapshot (<30 min) when the live source returns nothing … Shows 'src: CACHE'" | **Inaccurate in practice** (replay never triggers after ODPT failure, see A.0). Label text is actually `CACHE (N分前)`. |
| 8 | `README.md:335` | 「GTFS-Realtime（**真實即時誤點/警報**）…蓋到對應路線的班次上（`src: GTFS-RT`）」 | **Misleading**: per-row delays are the route-wide maximum, and the `GTFS-RT` label can sit on synthesized rows. |
| 9 | `README.md:342` | 「來源鏈：`GTFS-RT → ODPT → CACHE → STATIC`…（**不偽造班次**）」 | **Inaccurate**: real order is `ODPT → STATIC` (→ `CACHE` only if empty) then GTFS-RT overlay; "does not fabricate trains" contradicts `StaticSource`. |
| 10 | `README.en.md` / `README.ja.md` | — | **Parity gap**: the zh-TW-only section 「即時感功能」 (countdown/timeline/alerts/cache/GTFS-RT) is missing from en/ja. |
| 11 | `cli.py:90-95` (argparse `description`) | "Terminal split-flap JR / Toei departure board…" | Not false, but no disclosure that times are estimated; also omits Tokyo Metro & non-Tokyo lines. |
| 12 | `cli.py:270-272` (`--timeline` help) | "a first→last train bar … and a ⚠ **last-train alert** when service is closing" | **Risky**: `first_train`/`last_train` are unverified, line-level (not station-level) LLM values. A last-train warning built on them can be wrong by tens of minutes for a given station/direction (see B.3). |
| 13 | `cli.py:261` (`--countdown`) | "Show **live** 'あと N 分'" | Fine ("live" = ticking), but under `STATIC` it counts down to a synthesized train. |
| 14 | `pyproject.toml` `description` | "Terminal split-flap (Solari) departure board for JR / Tokyo Metro / Toei lines." | **Accurate** (no realism claim); incomplete (50 lines incl. Kansai/Hokkaido/Kyushu). |
| 15 | On-board `src: STATIC` | — | Literally true about the code path, but readers parse "STATIC" as "static (published) timetable". **Should change** (A.3). |
| 16 | On-board `src: ODPT` | — | Accurate (published schedule), but note holiday calendar bug and post-midnight drop. |
| 17 | On-board `src: CACHE (N分前)` | — | Honest about age; does not filter departed trains; practically unreachable (A.0). |
| 18 | On-board `src: GTFS-RT` | — | **Misleading** when base is STATIC; should be composite (A.3). |
| 19 | On-board `src: AGENDA` | — | Accurate. |

### A.2 Proposed rewording (drop-in)

**Tagline (README line 16)**

- zh-TW: 「每次刷新會先像老火車站、航站樓的機械翻牌那樣亂數翻滾，再逐格鎖定成下一班車的資訊。預設顯示的是依各線班距**推算的模擬時刻**（非官方時刻表）；設定 ODPT 金鑰後，支援的路線會改用 ODPT 提供的**官方時刻表**。」
- en: "Every refresh scrambles like an old mechanical flap board, then locks character-by-character into the next departures. By default those times are **simulated from each line's typical headways** (not an official timetable); with an ODPT key, supported lines show the **operator's published timetable** instead."
- ja: 「更新のたびに昔ながらのフラップ式案内板のように回転し、一文字ずつ次の発車情報へと確定します。標準では各路線の運転間隔から**推定した模擬時刻**を表示します（公式時刻表ではありません）。ODPT キーを設定すると、対応路線では ODPT が提供する**公式時刻表**を表示します。」

**Feature bullet (README `真實資料` / "Real data" / 「本物のデータ」)**

- zh-TW: 「**資料來源誠實標示**：設定 `ODPT_KEY` 後，支援的路線（東京地鐵、都營等）使用 ODPT 的官方**時刻表**（排定時刻，非即時位置）；未設定或取得失敗時，改以各線班距**推算**時刻，並標示 `src: 推定`。推算值不含實際首末班、臨時列車或假日特別時刻，**請勿用來趕末班車**。」
- en: "**Honest provenance**: with `ODPT_KEY`, supported lines (Tokyo Metro, Toei, …) use ODPT's published **timetable** (scheduled times, not real-time positions). Without a key, or if the fetch fails, times are **estimated** from typical headways and labelled `src: EST`. Estimates ignore real first/last trains, extra services and holiday timetables — **don't rely on them to catch a last train**."
- ja: 「**データ源の明示**：`ODPT_KEY` を設定すると、対応路線（東京メトロ・都営など）は ODPT の公式**時刻表**（計画ダイヤ。リアルタイムの在線位置ではありません）を使用します。キー未設定・取得失敗時は運転間隔から**推定**した時刻を表示し、`src: 推定` と表示します。推定値は実際の始発・終電、臨時列車、祝日ダイヤを反映しません。**終電の判断には使わないでください**。」

**Source-chain note (README.md:342)** — replace with:

- zh-TW: 「實際順序：`ODPT`（官方時刻表）→ 失敗則 `推定`（班距推算）；`--cache-dir` 只在前兩者都沒有資料時回放快取；GTFS-RT 只**疊加**誤點/警報，不會產生班次。若底層是推算資料，標籤會顯示 `推定+RT`。」
- en: "Actual order: `ODPT` (published timetable) → on failure `EST` (headway estimate); `--cache-dir` replays only when both return nothing; GTFS-RT only **overlays** delays/alerts and never creates departures. If the base rows are estimates the label reads `EST+RT`."
- ja: 「実際の順序：`ODPT`（公式時刻表）→ 失敗時は `推定`（運転間隔から推定）。`--cache-dir` は両方とも結果がない場合のみキャッシュを再生します。GTFS-RT は遅延・運行情報を**重ねるだけ**で、列車を生成しません。下地が推定の場合は `推定+RT` と表示します。」

**`--cache-dir` help** (only if the behaviour is fixed to replay *before* falling back to STATIC; otherwise say what it does today): "Cache ODPT departures as JSONL; if ODPT fails, replay the newest snapshot younger than 30 min (departed trains are dropped) before falling back to estimated times. Shows 'src: CACHE (N分前)'."

**argparse description**: "Terminal split-flap departure board for 50 Japanese rail lines. Times are estimated from typical headways unless ODPT_KEY is set (published timetable for supported operators)."

**pyproject description**: "Terminal split-flap (Solari) departure board for Japanese rail lines — estimated times offline, ODPT timetables optional." (≤ 1 line, keeps PyPI card honest.)

### A.3 On-board label recommendation

Yes — change it.

| Today | Proposed | Why |
|---|---|---|
| `src: STATIC` | `src: 推定` (ja/zh) with `EST` as ASCII fallback, or a single `src: EST` everywhere | "STATIC" reads as "static timetable". 推定 is understood by both Japanese and Chinese readers. |
| `src: GTFS-RT` on STATIC base | `src: EST+RT` / `推定+RT` | Don't let the overlay launder synthesized rows. |
| `src: GTFS-RT` on ODPT base | `src: ODPT+RT` | Keeps both facts. |
| statusline / minitable / timeline (no label today) | prefix estimated times with `≈` (1 column) or append a dim `推定` tag when the budget allows | These are the default Claude Code integrations; today they disclose nothing. |
| `CACHE (N分前)` | keep, but drop rows with `time < now` | Honest age, but no stale rows. |

Tests to add (all offline): `get_departures` with no key returns label `EST`; GTFS-RT overlay over STATIC returns `EST+RT`; `statusline_text` output for an EST source contains `≈` or `推定`; `StaticSource` at 03:00 returns `[]` or first-train rows only (see action list).

---

## B. Line data audit

### B.1 Structural validator (all 50 files)

Script: `validate_lines.py` (stdlib; `python3 -I validate_lines.py <repo>/jrboard/data`). Raw output: `validator-output.txt` (475 FAIL / 197 WARN lines). Grouped:

| Class | Lines | Count | Real problem? |
|---|---|---|---|
| `number` and `odpt_station` empty; `id` != `symbol+number` | all 10 `shinkansen-*` | 428 | **By design** (README says Shinkansen codes are invented). Breaks the `id == symbol+number` invariant; `odpt_railway` empty, so ODPT/GTFS-RT can never apply. |
| **Headway `0` means "no trains" in the data, but `StaticSource` turns `0` (and missing hours) into a 5-minute headway** | 28 lines use `0`; every line lacks hours 02-04 | - | **Yes - the main data/code contract bug.** `shinkansen-hokkaido` weekday `{"8":0,"14":0,"19":0,"21":0,...}` -> board shows a Hokkaido Shinkansen **every 5 min** in those hours; `shinkansen-tokaido` `{"23":0,"0":0,"1":0}` -> every 5 min overnight. |
| In-service hour with no positive headway (first train in hour 4) | chuo, keihintohoku, osaka-loop, saikyo, shonanshinjuku, sobu, yamanote, yokosuka | 16 | Minor (5-min fallback). |
| Positive headway outside `first_train..last_train` | hour `1` in 17 lines; hour `5` in 3 Sapporo lines (first train 06:00); hours `0`,`1` in otaru-hakodate, shonanshinjuku | 46 WARN | Inconsistent data (harmless today only because first/last are ignored). |
| `odpt_station` suffix contains hyphens (`Kita-sanjuyojo`, `BusCenter-mae`) | 3 Sapporo lines | 26 | ODPT ids never contain hyphens; moot, Sapporo is not on ODPT (B.4 #13). |
| `kana` not pure hiragana | yamanote JY26, keihintohoku JK21 (`たかなわゲートウェイ`) | 2 | Style (reading たかなわげーとうぇい). |
| `id` != `symbol+number` | keiyo `JE-SOGA` (number empty), oedo `E28L` | 2 | Deliberate: 蘇我 has **no JE number** ("蘇我駅は未導入", [ja.wikipedia 京葉線](https://ja.wikipedia.org/wiki/京葉線)); 都庁前 is visited twice on the 6-shaped Oedo line. Document the exception. |
| Duplicate `name_jp` | oedo 都庁前 x2 | 1 WARN | as above |
| Non-contiguous numbering | keio (KO01->KO04), oedo, osaka-loop | 3 WARN | keio correct (B.5), oedo correct, **osaka-loop wrong** (B.4). |
| Romaji style | macrons only in ginza, sobu (`Omote-sandō`, `Kyōbashi`); 45 lines none; hyphenation varies | - | Inconsistent house style. |
| loop flag; HH:MM; colour hex/ANSI agreement; unique ids; required fields; headways within 2-60 min | all | 0 | OK |

### B.2 Station lists vs reference sources

Method: (1) automated cross-check of all 50 lines against the sibling `tokyo-metro-challenge` repo's `data/*.json` (`crosscheck_sibling.py` -> `crosscheck-output.txt`; `order_recheck.py`); (2) every disagreement checked against ja.wikipedia or the operator; (3) ODPT ids checked against **official ODPT data** (Toei, CC BY 4.0, `api-public.odpt.org`) and **Mini Tokyo 3D** `stations.json` (MIT, ODPT-derived ids, [github](https://github.com/nagix/mini-tokyo-3d/blob/master/data/stations.json)).

| Result | Lines |
|---|---|
| Count, termini, order, names agree with sibling (33) | asakusa, chuo, fukuoka-kuko, fukutoshin, ginza, hanzomon, hibiya, keihintohoku, keiyo, kyoto-karasuma, kyoto-tozai, mita, nagoya-higashiyama, namboku, osaka-chuo, osaka-tanimachi, sapporo-namboku, sapporo-toho, sapporo-tozai, shinjuku, shinkansen-hokkaido/-kyushu/-nishikyushu/-sanyo/-tohoku/-tokaido, sobu, tokyu-toyoko, tozai, yamanote, yokohama-blue, yokosuka, yurikamome |
| Agree after deliberate scope (13) | chiyoda (北綾瀬 branch omitted), marunouchi (方南町 branch omitted), saikyo (ends 大宮; 川越線 omitted), shinkansen-akita/-yamagata/-hokuriku/-joetsu (Tokyo-side stops prepended; core order contiguous), yurakucho (麹町 vs 麴町), osaka-midosuji (難波 vs なんば), kyoto-keihan (adds 鴨東線 出町柳・神宮丸太町), keio (初台・幡ヶ谷 omitted), oedo (6-shape) |
| **Disagreement confirmed as error** | kyoto-sagano, osaka-loop (B.4) |
| Not in sibling; checked on ja.wikipedia | kyoto-randen (13 stations, termini, A1-A5 order, 西院=さい), otaru-hakodate (count/termini; numbering wrong, B.4) |
| Numbering not checkable | shonanshinjuku - JS numbering exists for 大宮-逗子 since 2016-10-01 ([ja.wikipedia 湘南新宿ライン](https://ja.wikipedia.org/wiki/湘南新宿ライン)); individual JS numbers **not verified** |

### B.3 First/last train spot-checks

jrboard stores one `first_train`/`last_train` per **line**, so I compare with the earliest/latest departure anywhere on the line.

| Line | jrboard | Reference | Verdict | Source |
|---|---|---|---|---|
| asakusa | 05:00 / 00:32 | 05:00 / **00:30** | last +2 (claims a train that doesn't exist) | Toei GTFS, feed 2026-03-14..2027-03-12, CC BY 4.0, [api-public](https://api-public.odpt.org/api/v4/files/Toei/data/Toei-Train-GTFS.zip) (`toei_firstlast.py`) |
| mita | 05:00 / 00:25 | 05:00 / **00:43** | last -18 | same |
| shinjuku | 05:00 / 00:20 | 05:00 / **00:27** | last -7 | same |
| oedo | 05:00 / 00:14 | 05:00 / **00:57** | last -43 | same |
| sapporo-namboku | 06:00 / 00:00 | 06:00 / 00:00 (麻生発, weekday & 土日祝) | OK | [札幌市交通局 麻生駅時刻表, updated 2026-08-01](https://www.city.sapporo.jp/st/subway/route_time/h26/n01.html) |
| fukuoka-kuko | 05:30 / 23:46 | regular last departures 姪浜 0:00, 天神 0:12 (2024); later on Fridays and (per 2026 reports) Mon-Sat from 2026-04-01 | **last wrong (>=14 min early)** | [福岡市交通局 press release 2024-08-19, 別紙](https://www.city.fukuoka.lg.jp/shisei/mayor/interviews/documents/kaiken2_frydaynighttraingakaettekita_maisyuukinnyounosyuudennwoenntyousimasu.pdf); 2026 change only via search snippet |
| yamanote | 04:26 / 01:18 | 04:25 (池袋, 外回り) / ~01:03 (池袋, 内回り) | suspected last ~15 min late | [JR East 外回り](https://timetables.jreast.co.jp/2611/timetable-v/630d1.html), [内回り](https://timetables.jreast.co.jp/2611/timetable-v/630u1.html) (values from a summarising fetcher - verify by eye) |
| nagoya-higashiyama | 05:34 / 23:45 | first 05:34 高畑発 | first OK; last not checked | [ekispert](https://roote.ekispert.net/timetable/train/25017/5371) via search snippet (secondary) |

First trains are mostly right; **last trains are wrong in 5 of 7 lines checked**, by -43..+2 min. That is the field the `--timeline` last-train alert relies on.

### B.4 Confirmed errors

| # | File | Field | Current | Correct | Source |
|---|---|---|---|---|---|
| 1 | kyoto-sagano.json | stations | 15, no 梅小路京都西 | insert **梅小路京都西 (JR-E02)** between 京都 and 丹波口 (opened 2019-03-16) -> 16 | [ja.wikipedia 嵯峨野線](https://ja.wikipedia.org/wiki/嵯峨野線) |
| 2 | kyoto-sagano.json | stations[1..14].id/number | 丹波口 E02 ... 園部 E15 | 丹波口 **E03** ... 吉富 **E15**, 園部 **E16** | same |
| 3 | osaka-loop.json | id/number (17 of 19) | 大阪 O11, 天満 O12 ... 寺田町 O20, 新今宮 O02 ... 福島 O09 | 天王寺 O01, 寺田町 O02, 桃谷 O03, 鶴橋 O04, 玉造 O05, 森ノ宮 O06, 大阪城公園 O07, 京橋 O08, 桜ノ宮 O09, 天満 O10, 大阪 O11, 福島 O12, 野田 O13, 西九条 O14, 弁天町 O15, 大正 O16, 芦原橋 O17, 今宮 O18, 新今宮 O19 | [ja.wikipedia 大阪環状線](https://ja.wikipedia.org/wiki/大阪環状線) (O01 天王寺 0.0 km, O11 大阪 10.7 km; 新今宮->天王寺 closes the loop); sibling agrees |
| 4 | otaru-hakodate.json | symbol, id/number | `H`; 小樽 H01 ... 札幌 H15 | 小樽 **S15**, 南小樽 **S14**, ..., 桑園 **S02**, 札幌 **01** | [ja.wikipedia 小樽駅](https://ja.wikipedia.org/wiki/小樽駅); [JR北海道 駅ナンバリング](https://ja.wikipedia.org/wiki/北海道旅客鉄道の駅ナンバリング・区間カラー) |
| 5 | asakusa.json | odpt_station | `Asakusa.Nishimagome`, `.Higashiginza`, `.Higashinihombashi`, `.Honjoazumabashi` | `.NishiMagome`, `.HigashiGinza`, `.HigashiNihombashi`, `.HonjoAzumabashi` (case-sensitive; wrong id -> empty ODPT result -> silent STATIC) | official [ODPT Toei StationTimetable](https://api-public.odpt.org/api/v4/odpt:StationTimetable?odpt:operator=odpt.Operator:Toei) (149 station ids) |
| 6 | mita.json | odpt_station | `Mita.Itabashikuyakushomae` | `Mita.ItabashiKuyakushomae` | same |
| 7 | shinjuku.json | odpt_station | `.Shinjukusanchome`, `.Bakuroyokoyama`, `.Nishiojima`, `.Higashiojima` | `.ShinjukuSanchome`, `.BakuroYokoyama`, `.NishiOjima`, `.HigashiOjima` | same |
| 8 | asakusa.json | last_train | 00:32 | 00:30 | Toei GTFS |
| 9 | mita.json | last_train | 00:25 | 00:43 | Toei GTFS |
| 10 | shinjuku.json | last_train | 00:20 | 00:27 | Toei GTFS |
| 11 | oedo.json | last_train | 00:14 | 00:57 | Toei GTFS |
| 12 | fukuoka-kuko.json | last_train | 23:46 | >= 00:12 (2024 regular timetable); re-check against the 2026-04 timetable | Fukuoka 2024-08-19 |
| 13 | 15 lines on operators not on ODPT (Sapporo x3, OsakaMetro x3, JR-West x2, Kyoto x2, Keihan, Keifuku, Nagoya, Fukuoka, JR-Hokkaido) | odpt_railway / odpt_station | e.g. `odpt.Railway:Sapporo.Namboku` | No such ODPT railway; ids are invented. None of these operators has a rail dataset in the ODPT catalogue (386 datasets scraped; only Kyoto City Subway GTFS, challenge-only). Blank them or rename the field. | [ckan.odpt.org/dataset](https://ckan.odpt.org/dataset/) (all pages; `dl-ckan/slugs.txt`) |

**Tally:** 1 missing station; 14 + 17 + 15 wrong station numbers (sagano, osaka-loop, otaru-hakodate); 10 wrong ODPT station ids; 5 wrong `last_train`; invented ODPT ids on 15 lines.

### B.5 Suspected (verify before changing)

| File | Field | Observation | Why unconfirmed |
|---|---|---|---|
| Tokyo Metro (ginza 5, hibiya 6, chiyoda 1, hanzomon 2, marunouchi 13, tozai 6, yurakucho 6, fukutoshin 8) | odpt_station | **48 ids** differ in casing from Mini Tokyo 3D (`Ginza.Aoyamaitchome` vs `AoyamaItchome`, `Omotesando` vs `OmoteSando`, `Hibiya.Hiroo` vs `HiroO`) | Same pattern as the 10 confirmed Toei errors, but Tokyo Metro ODPT needs a key; not called. |
| saikyo.json | odpt_railway | `JR-East.Saikyo` absent from Mini Tokyo 3D (`JR-East.SaikyoKawagoe` exists) | JR East ODPT data is challenge-only |
| shonanshinjuku.json | odpt_station | 北鎌倉/鎌倉/逗子 under `ShonanShinjuku` absent in MT3D | same |
| sobu.json | odpt_station | `MakuhariHongo`/`Motoyawata` vs MT3D `Makuharihongo`/`MotoYawata` | same |
| yamanote.json | first/last | 04:26/01:18 vs 04:25/~01:03 | fetcher extraction |
| chiyoda.json | name_en C03/C10 | `Meiji-jingumae 'Harajuku'` - odd quoting | cosmetic |
| sapporo-*, osaka-tanimachi, keiyo | name_en | `Kita-sanjuyojo`, `Tenjimbashisuji-rokuchome`, `Kasai-Rinkai Park` vs signage style `Kita 34-jo`, `Tenjimbashisuji 6-chome`, `Kasai-Rinkai-Koen` | sibling only |
| 21 lines | color.hex | differ from sibling (asakusa `#EC6E65` vs `#E85298`, shinjuku `#B0BF1E` vs `#6CBB5A`, all 10 Shinkansen, ...) | no single authoritative hex; not investigated |
| kyoto-keihan.json | name_jp | "京阪本線" but includes 鴨東線 | naming nuance |
| osaka-midosuji.json | M20 name_jp | `難波`; signage `なんば` (formal name 難波) | [ja.wikipedia 難波駅](https://ja.wikipedia.org/wiki/なんば駅) - both defensible |
| all | headway_min | never verified against a timetable | no source checked |

Checked and **not** errors: keio omits 初台・幡ヶ谷 (Keio Line trains never stop there, [ja.wikipedia 京王線](https://ja.wikipedia.org/wiki/京王線)); randen 西院 = さい ([ja.wikipedia 嵐山本線](https://ja.wikipedia.org/wiki/京福電気鉄道嵐山本線)); keiyo 蘇我 has no JE number.

### B.6 Coverage actually achieved

- Structural validation: **50/50** lines.
- Count + termini + order: **50/50** (48 vs sibling dataset = secondary; randen and otaru-hakodate vs ja.wikipedia).
- High-risk subset (25 lines): full order vs sibling for 23; randen order only A1-A5; otaru-hakodate count/termini + 4 station numbers.
- Primary-source confirmation only where the sibling disagreed (sagano, osaka-loop, keio, keiyo, namba) plus randen and otaru. **Lines where jrboard and the sibling agree were not re-checked against a primary source.**
- ODPT ids: 4 Toei lines vs official ODPT; 20 Kanto lines vs Mini Tokyo 3D.
- First/last: 8 lines (4 Toei from official GTFS; Sapporo, Fukuoka from operator; Yamanote from JR East pages; Nagoya first only, secondary).

---
## C. Japanese holidays under the zero-dependency constraint

### C.1 Options

| | (a) Vendored Cabinet Office CSV | (b) Algorithmic rules | (c) Optional dependency |
|---|---|---|---|
| What | [`syukujitsu.csv`](https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv): 21,538 B, Shift_JIS, 1,067 rows | 祝日法 rules + equinox approximation | [`jpholiday`](https://pypi.org/pypi/jpholiday/json) 1.0.3 / [`holidays`](https://pypi.org/pypi/holidays/json) 0.109 |
| Years | **1955-2027** (downloaded 2026-11-19) | equinox formula ~1980-2099; rules since 2007 (振替), 2016 (山の日), 2020 (天皇誕生日 2/23) | algorithmic / multi-country |
| License | Cabinet Office content: **公共データ利用規約（第1.0版）** unless noted ([内閣府ホームページ利用規約](https://www.cao.go.jp/notice/rule.html); [PDL 1.0](https://www.digital.go.jp/resources/open_data/public_data_license_v1.0)) - attribution, CC BY 4.0-compatible | own code | jpholiday **MIT**, wheel **16 KB**, no deps, py>=3.9 (2025-12-26); holidays **MIT**, wheel **1.74 MB**, needs python-dateutil, py>=3.11 (2026-11-17) |
| Update burden | Re-vendor **every year**: 春分/秋分 of year N+1 are fixed only when NAOJ publishes the 暦要項 in the 官報 in February of year N ([内閣府「国民の祝日」](https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html); [ja.wikipedia 春分の日](https://ja.wikipedia.org/wiki/%E6%98%A5%E5%88%86%E3%81%AE%E6%97%A5)). After 2027-12-31 a stale copy silently loses all holidays. | only on law changes (one-offs like 2019 即位, 2020/2021 Olympic moves) | upstream; but a runtime dependency |
| Zero-dep | yes | yes | no (unless optional extra) |

**Empirical check of (b)** (`holiday_rules_check.py`, ~90 lines, stdlib): 15 fixed/Happy-Monday holidays, 春分 = `int(20.8431 + 0.242194*(Y-1980) - (Y-1980)//4)` (March), 秋分 = same with 23.2488 (September), 2007+ 振替休日, 国民の休日 sandwich rule, and a 3-entry override table (2019, 2020, 2021) reproduce the official CSV with **0 mismatching days for 2007-2027**; the equinox formula matches **every year 1980-2027**.

### C.2 年末年始

National holidays cover only 1/1 (+振替). Operators run 土休日ダイヤ over a wider, operator-specific window:

| Operator | Window | Source |
|---|---|---|
| Tokyo Metro | 12/30-1/3 (2024-25; 2025-26) | [トラベル Watch 2024-25](https://travel.watch.impress.co.jp/docs/news/1649118.html) (links Tokyo Metro release `tokyometro.jp/info/219426.html`); 2025-26 via [tetsudo-ch](https://tetsudo-ch.com/13018418.html), [fun-japan](https://www.fun-japan.jp/jp/articles/13863) |
| Toei subway + 日暮里・舎人ライナー | 12/30-1/3 | [東京都交通局 2021-12 notice](https://www.kotsu.metro.tokyo.jp/pickup_information/news/subway/2021/sub_p_2021121710218_h.html) (pattern; 2025-26 notice not found) |
| Odakyu | 12/30-1/3 | トラベル Watch 2024-25 |
| **Sotetsu** | **12/28-1/5** | トラベル Watch 2024-25 |
| JR East (Kanto 在来線) | **not verified** - no JR East statement found | - |
| Sapporo subway | 土日祝ダイヤ over 年末年始 (dates not extracted) | [札幌市交通局 2024-2025](https://www.city.sapporo.jp/st/2024-2025.html) |

**Toei's own official GTFS does not encode the year-end window**: `calendar_dates.txt` (feed 20261009) flips only national holidays (e.g. 2027-01-01), not 12/30, 12/31, 1/2, 1/3. Even a GTFS-backed source needs a separate year-end rule. Also: ODPT uses four Toei calendars (`Weekday` 288 tables, `SaturdayHoliday` 230, `Holiday` 58, `Saturday` 58); `ODPTSource` only asks for the first two.

### C.3 Recommendation

**(b): algorithmic rules + small override table + per-line year-end window.** Zero-dependency, valid for decades, 0-diff vs the official list 2007-2027. Vendor `syukujitsu.csv` only as a **test oracle** under `tests/fixtures/` (with the 公共データ利用規約 credit), not at runtime. Add an optional `"holiday_window": ["12-30", "01-03"]` (default) per line JSON for Sotetsu-style operators. Skip `jpholiday`: it adds a dependency for what a 90-line function already does; `holidays` is 1.74 MB + dateutil.

### C.4 Test dates (Tokyo Metro/Toei-style line)

| Date | Why | Expected |
|---|---|---|
| 2026-11-23 Mon | 勤労感謝の日 | holiday |
| 2026-11-24 Tue | ordinary | weekday |
| 2026-09-22 Tue | 国民の休日 (between 9/21 敬老 and 9/23 秋分) | holiday |
| 2026-05-06 Wed | 振替休日 (5/3 Sun) | holiday |
| 2026-03-20 Fri | 春分の日 | holiday |
| 2027-03-22 Mon | 振替休日 (春分 3/21 Sun) | holiday |
| 2027-01-11 Mon | 成人の日 | holiday |
| 2026-12-29 Tue | before window | weekday |
| 2026-12-30 Wed, 2026-12-31 Thu | year-end window, not national holidays | holiday diagram |
| 2027-01-01 Fri | 元日 | holiday |
| 2027-01-02 Sat, 2027-01-03 Sun | window + weekend | holiday |
| 2027-01-04 Mon | after window | weekday |
| 2019-05-01 Wed | 即位の日 (override) | holiday |
| 2020-07-24 Fri / 2020-10-12 Mon | スポーツの日 moved / its usual date that year | holiday / weekday |
| every day 2016-2027 | vs `syukujitsu.csv` fixture | 0 diffs |

---

## D. Path to real timetables

### D.1 ODPT tiers and licenses (catalogue scraped 2026-11-19)

| Operator (jrboard lines) | Datasets | License / tier | Redistribute in an MIT PyPI package? |
|---|---|---|---|
| **Toei** (asakusa, mita, shinjuku, oedo) | [`r_station_timetable-toei`](https://ckan.odpt.org/dataset/r_station_timetable-toei), GTFS [`train-toei`](https://ckan.odpt.org/dataset/train-toei) | **CC BY 4.0**; **no key needed** via `api-public.odpt.org` | **Yes**, crediting "東京都交通局・公共交通オープンデータ協議会, <dataset>, CC BY 4.0" ([ODPT FAQ](https://developer.odpt.org/ja/faq-info#cc-by-credit)) |
| **Tokyo Metro** (9) | [`r_station_timetable-tokyometro`](https://ckan.odpt.org/dataset/r_station_timetable-tokyometro), [`train-tokyometro`](https://ckan.odpt.org/dataset/train-tokyometro) | 公共交通オープンデータ基本ライセンス; key required | **No.** 基本ライセンス **第8条（禁止事項）1** forbids publishing/redistributing the data, copies, or derived data from which all or most of the original can be restored, paid or free, in a form third parties can reuse - unless the dataset's 特定利用条件 says otherwise ([developer.odpt.org/terms/data_basic_license.html](https://developer.odpt.org/terms/data_basic_license.html); SPA - clause text read from its JS bundle) |
| **Yokohama Municipal** (yokohama-blue) | [`r_station_timetable-yokohamamunicipal`](https://ckan.odpt.org/dataset/r_station_timetable-yokohamamunicipal), [`yokohama_municipal_train`](https://ckan.odpt.org/dataset/yokohama_municipal_train) | 基本ライセンス (+特定利用条件) | **No** |
| **Yurikamome** | [`r_station_timetable-yurikamome`](https://ckan.odpt.org/dataset/r_station_timetable-yurikamome) | 基本ライセンス | **No** |
| **JR East** (8) | [`jreast__r_station_timetable`](https://ckan.odpt.org/dataset/jreast__r_station_timetable), GTFS [`jreast_tokyo_area`](https://ckan.odpt.org/dataset/jreast_tokyo_area), GTFS-RT [`odpt_jreast_tokyo_area`](https://ckan.odpt.org/dataset/odpt_jreast_tokyo_area) | **【チャレンジ2026限定】 公共交通オープンデータチャレンジ限定ライセンス**: challenge period only, for challenge entries, no third-party provision | **No** (a normal `ODPT_KEY` can't see it) |
| **Keio**, **Tokyu** | `keio__r_station_timetable`, `keio_train`, `tokyu__r_station_timetable` | challenge-limited | **No** |
| Kyoto City Subway | [`kyoto_municipal_transportation_kyoto_city_subway_gtfs`](https://ckan.odpt.org/dataset/kyoto_municipal_transportation_kyoto_city_subway_gtfs) | 基本ライセンス, published only during the challenge | **No** |
| Sapporo, Nagoya, Osaka Metro, JR West, JR Hokkaido, JR Central/Kyushu, Keihan, Keifuku, Fukuoka | none on ODPT | - | n/a. Other publishers **not investigated**. |

Consequences: with a standard key at most **15/50 lines** can get ODPT departures, and 58 of their station ids are mis-cased (10 confirmed, 48 suspected), so fewer stations actually work; every failure silently becomes STATIC. Conversely **Toei works with no key** via `api-public`. `docs/LIVE-DATA-APIS.md` ("JR East 提供 GTFS+GTFS-RT ... 免費") should say it is challenge-only.

### D.2 Size and cadence (measured on Toei)

| Artifact | Size |
|---|---|
| Toei rail GTFS zip (4 subway lines + tram + liner) | 779,700 B; `stop_times.txt` 5.1 MB unzipped |
| ODPT StationTimetable, all Toei | 25 MB JSON (634 tables) |
| One station (新宿線 新宿, Eastbound, Weekday+SaturdayHoliday, 373 departures) | 86 KB JSON / 4.8 KB gzip; **11.6 KB / 1.1 KB gzip** as compact `[time, dest, type]` rows |

~10 flagship Toei stations ~= 120 KB raw (~12 KB gzipped).

Cadence: Toei GTFS is valid **2026-03-14 -> 2027-03-12** (`feed_info.txt`, `feed_version 20261009`), i.e. the usual mid-March ダイヤ改正; operators also revise mid-year (Fukuoka 2026-03-16 and 2026-04-01). The ODPT Toei StationTimetable records carry `dct:issued` 2025-03-15/17 while the GTFS starts 2026-03-14 - check they agree before snapshotting; prefer GTFS.

### D.3 Recommendation

1. **Bundle real snapshots only for Toei** (CC BY 4.0): offline script from the official GTFS -> compact per-station JSON with `valid_from/valid_to` + attribution; label `src: 時刻表 (2026-03-14)`; fall back to `推定` outside the validity window.
2. **Tokyo Metro / Yokohama / Yurikamome**: runtime fetch with the user's key, cache locally (publishing the cache is what 第8条 forbids). Fix id casing first.
3. **JR East / Keio / Tokyu / Kyoto**: don't ship, don't advertise.
4. **Everything else** stays `推定` until an open, redistributable GTFS-JP source is found (not researched).
5. Use `api-public.odpt.org` so Toei works without `ODPT_KEY`.

---

## E. tokyo-metro-challenge dataset as cross-check / generator

`tokyo-metro-challenge/data/` (sibling repo): `stations.json` (built from Mini Tokyo 3D, MIT, by `scripts/build-data.mjs`, which asserts official station counts - 14 `count:` assertions) + 24 edition files declaring "Company station lists and ja.wikipedia (2026-10); coordinates © OpenStreetMap contributors (ODbL)". `package.json` says MIT; there is no LICENSE file.

### E.1 Field mapping

| jrboard `data/<key>.json` | sibling field | Notes |
|---|---|---|
| key | - | derive from file + `lines[].code` |
| name_jp | `lines[].ja` | no operator prefix (銀座線 vs 東京メトロ銀座線) |
| name_en | `lines[].en` | |
| symbol | `lines[].prefix` or `code` | Shinkansen codes differ (TK/SY vs TKD/SYO); JR through-lines differ (JOY vs JO/JS) |
| color.hex | `lines[].color` | 21 lines differ |
| color.name, ansi_fg, ansi_bg | - | ANSI derivable from hex (`scripts/apply_colors.py`) |
| operator | `lines[].company` (newer editions), file `operators` map; `op` is only `metro`/`jr` | |
| odpt_railway | - | build script segment `src` (`TokyoMetro.Ginza`) = ODPT id without prefix, Metro/Toei only |
| loop | `paths[0][0] == paths[0][-1]` | derivable |
| station order | `lines[].paths` (station-id arrays; several for branches) | |
| stations[].id/number | `stations[].numbers` filtered by line prefix | empty where no official number (蘇我, Shinkansen) |
| stations[].name_jp | `stations[].ja` | signage forms (なんば, 麴町) |
| stations[].kana | **absent** | Mini Tokyo 3D has no `ja-Hrkt` either (0/2,610) |
| stations[].name_en | `stations[].en` | signage style (`Kita 34-jo`) |
| stations[].odpt_station | **absent** | Mini Tokyo 3D `stations.json` ids (e.g. `TokyoMetro.Ginza.AoyamaItchome`) cover Kanto lines - and exposed jrboard's 58 casing errors |
| timetable.* | **absent** | no times, headways, directions or tracks |
| - | lat, lon, zh, zhHans, aliases | extra |

### E.2 Coverage

48/50 jrboard lines have a matching sibling line. **Not covered:** kyoto-randen (only 阪急嵐山線 present), otaru-hakodate (no JR Hokkaido line). Akita/Yamagata/Hokuriku/Joetsu Shinkansen: official section only.

### E.3 Could jrboard station lists be generated from it?

**Yes for names, order, counts and station numbers of 48 lines; no for kana, ODPT ids and anything in `timetable`.** A generator needs: sibling (names/order/numbers) + Mini Tokyo 3D (ODPT ids, Kanto) + a kana source (none found) + hand-kept timetable blocks. Use only names/order/numbers (facts), drop lat/lon to avoid ODbL share-alike, credit Mini Tokyo 3D (MIT). Best use: a **CI cross-check**, not the source of truth (it is itself secondary and uses different name styles).

---

## Prioritized action list

| P | Action | Test / verification |
|---|---|---|
| **P0** | `StaticSource`: respect `first_train`/`last_train`; headway `0`/missing = no trains (not 5 min). | `ginza` @ 03:00 -> `[]` or first row >= 05:01; `shinkansen-hokkaido` @ 08:00 weekday -> next row in hour 9; `shinkansen-tokaido` @ 23:30 -> next row >= 06:00. |
| **P0** | Label `STATIC` -> `推定`/`EST`; composite `EST+RT`/`ODPT+RT`; estimate marker in statusline/minitable/timeline. | No key -> label `EST`; GTFS-RT over STATIC -> `EST+RT`; statusline golden contains `≈` or `推定`. |
| **P0** | Rewrite README claims A.1 #1-#3, #7-#9 in all three languages (A.2); move the "times are estimated" sentence out of the Shinkansen subsection; fix "20 lines". | Test greps READMEs for `真實的到站|real upcoming|実際の次の発車|真實靜態|realistic static|現実的な静的|不偽造班次` -> no match. |
| **P0** | No ⚠ last-train alert (or label it 推定) unless the source is a real timetable. | `render_timeline` with source `EST` renders no `⚠` (or renders `推定`). |
| **P1** | Fix confirmed data errors B.4 #1-#13. | `tests/test_line_facts.py`: sagano has 梅小路京都西 = E02 and 16 stations; osaka-loop 福島 = O12, 新今宮 = O19; otaru 小樽 = S15; Toei ids are in a 149-id fixture from `api-public`; Toei `last_train` = GTFS values. |
| **P1** | Holiday logic per C.3 in both `StaticSource` and `ODPTSource`. | C.4 as parametrised tests + 2016-2027 oracle test vs vendored `syukujitsu.csv`. |
| **P1** | `--cache-dir`: replay before falling back to STATIC; drop departed rows. | ODPT raises + fresh snapshot -> label `CACHE (N分前)`, no row earlier than now. |
| **P1** | Fix 48 suspected Tokyo Metro id casings after one keyed check per line; blank invented `odpt_railway` on 15 lines. | Keyed integration (skipped without key): every `odpt_station` returns >= 1 table. Offline: ids are a subset of a Mini Tokyo 3D fixture. |
| **P1** | GTFS-RT: per-trip delay (or none per row); empty `informed_entity` alerts must not match every line. | Synthetic `FeedMessage` with trips delayed 2 and 9 min -> rows are not all `+9`. |
| **P2** | ODPT: Toei via `api-public` without key; keep post-midnight departures. | At 23:50, an ODPT `00:05` row is kept and sorted last. |
| **P2** | Ship Toei flagship snapshots (D.3) with attribution + validity window. | Snapshot outside `valid_to` -> `推定`; NOTICE contains the CC BY credit. |
| **P2** | Optional CI job running `crosscheck_sibling.py` (skip if sibling path absent). | Non-zero exit on new disagreements. |
| **P3** | Romaji house style; chiyoda `name_en` quoting; document `JE-SOGA`/`E28L` in the schema. | Validator romaji rule passes for all 50 files. |
| **P3** | `docs/LIVE-DATA-APIS.md`: JR East GTFS/GTFS-RT is challenge-only; Tokyo Metro data is not redistributable. | Doc review. |
