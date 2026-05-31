export const meta = {
  name: 'jr-board-expand-jr-lines',
  description: 'Generate JSON data for major Tokyo-area JR East commuter lines (Chuo, Sobu, Keihin-Tohoku, Saikyo, Shonan-Shinjuku, Yokosuka) following the fixed data contract, then verify',
  phases: [
    { title: '生成 JR 線資料', detail: 'one agent per JR line writes data/<key>.json' },
    { title: '驗證', detail: 'engine lists/renders the new JR lines' },
  ],
}

const PROJECT = '/Users/minghsuan/Downloads/JR-timetable'
const PKG = `${PROJECT}/jrboard`

const DATA_CONTRACT = `
Write ONE JSON file at ${PKG}/data/<key>.json with this exact schema (no comments in the real file):
{
  "key": "<lowercase file basename>",
  "name_jp": "...", "name_en": "...",
  "symbol": "<JR East line code shown in the station-number badge, e.g. JC, JB, JK, JA, JS, JO>",
  "color": { "name": "...", "ansi_fg": "\\u001b[38;5;<n>m", "ansi_bg": "\\u001b[48;5;<n>m\\u001b[38;5;<fg>m", "hex": "#RRGGBB" },
  "operator": "JR-East",
  "odpt_railway": "odpt.Railway:JR-East.<Line>",
  "loop": false,
  "stations": [
    { "id": "<symbol+number e.g. JC01>", "number": "01", "name_jp": "...", "kana": "<hiragana>", "name_en": "<official Hepburn>", "odpt_station": "odpt.Station:JR-East.<Line>.<RomajiNoSpaces>" }
    // ALL real stations on the standard service section, REAL running order
  ],
  "timetable": {
    "first_train": "HH:MM", "last_train": "HH:MM",
    "headway_min": {
      "weekday": { "5": .., "6": .., "7": .., "8": .., "9": .., "10": .., "11": .., "12": .., "13": .., "14": .., "15": .., "16": .., "17": .., "18": .., "19": .., "20": .., "21": .., "22": .., "23": .., "0": .., "1": .. },
      "holiday": { ...same hour keys... }
    },
    "directions": [
      { "id": "<a>", "name_jp": "<terminus>方面", "via_jp": "<major via>方面", "track": "1" },
      { "id": "<b>", "name_jp": "<terminus>方面", "via_jp": "<major via>方面", "track": "2" }
    ]
  }
}
RULES:
- Stations MUST be REAL, in REAL running order, for the line's STANDARD service section (see per-line note). kana = hiragana. name_en = official Hepburn (hyphenate compounds: Nishi-Kokubunji, Shin-Koiwa, etc.).
- color.hex MUST be the official JR East line colour; pick the closest xterm-256 code for ansi_fg/ansi_bg with a readable contrasting foreground in ansi_bg.
- headway realistic (rush denser). directions = the two real termini of that section.
- Validate the JSON parses before finishing. Return a short confirmation only; do NOT dump file contents.
`

const LINES = [
  { key: 'chuo',     desc: 'JR中央線快速 (Chuo Line Rapid). symbol "JC", odpt.Railway:JR-East.ChuoRapid. Official colour vermilion orange #F15A22. Standard rapid section 東京(JC01)↔高尾(JC24): 東京/神田/御茶ノ水/四ツ谷/新宿/中野/...(rapid skips some)/三鷹/国分寺/立川/八王子/高尾. Use the official JC station-number list. Termini: 東京方面 / 高尾方面.' },
  { key: 'sobu',     desc: 'JR中央・総武線各駅停車 (Chuo-Sobu Line Local). symbol "JB", odpt.Railway:JR-East.ChuoSobuLocal. Official colour canary yellow #FFD400. Section 三鷹(JB01)↔千葉(JB39): 三鷹/吉祥寺/中野/新宿/御茶ノ水/秋葉原/錦糸町/...船橋/千葉. ~39 stations. Termini: 三鷹方面 / 千葉方面.' },
  { key: 'keihintohoku', desc: 'JR京浜東北・根岸線 (Keihin-Tohoku–Negishi Line). symbol "JK", odpt.Railway:JR-East.KeihinTohokuNegishi. Official colour light blue/cyan #00B2E5. Section 大宮(JK47)↔大船(JK01) (note JR numbers Keihin-Tohoku southbound: 大宮 high number ... 横浜 ... 大船 low; encode in service order 大宮→東京→横浜→大船 and set number per official JK code). ~46 stations. Termini: 大宮方面 / 大船方面.' },
  { key: 'saikyo',   desc: 'JR埼京線 (Saikyo Line). symbol "JA", odpt.Railway:JR-East.Saikyo. Official colour green #00AC9A. Core section 大崎(JA08)↔大宮(JA27ish) via 渋谷/新宿/池袋/赤羽/武蔵浦和: encode 大崎→恵比寿→渋谷→新宿→池袋→板橋→赤羽→武蔵浦和→大宮. Use official JA numbers. Termini: 大崎方面 / 大宮方面.' },
  { key: 'shonanshinjuku', desc: 'JR湘南新宿ライン (Shonan-Shinjuku Line). symbol "JS", odpt.Railway:JR-East.ShonanShinjuku. Official colour red #E60012 (confirm). Use the principal stops 大宮/浦和/赤羽/池袋/新宿/渋谷/恵比寿/大崎/西大井/武蔵小杉/横浜/...大船/藤沢/...小田原 — encode the commonly-served stop list with JS numbers. Termini: 宇都宮/高崎方面 / 小田原/逗子方面 (use simplified 北行/南行 via majors).' },
  { key: 'yokosuka', desc: 'JR横須賀線 (Yokosuka Line). symbol "JO", odpt.Railway:JR-East.Yokosuka. Official colour navy blue #0067C0. Section 東京(JO19)↔久里浜(JO01) via 新橋/品川/西大井/武蔵小杉/横浜/大船/鎌倉/逗子/久里浜. Encode in service order with official JO numbers. Termini: 東京方面 / 久里浜方面.' },
]

phase('生成 JR 線資料')
const results = await parallel(LINES.map(L => () => agent(
  `Gather REAL data and WRITE the file ${PKG}/data/${L.key}.json. Accuracy matters — real transit data.\n\n` +
  `Line: ${L.desc}\n\n` +
  `Follow this contract EXACTLY:\n${DATA_CONTRACT}\n\n` +
  `Sources: Wikipedia line article + official JR East station list for order/readings/Hepburn and the JR station-number (e.g. JC01). Cross-check the station COUNT. Create ${PKG}/data if missing. NOTE: the file key "${L.key}" must not collide with existing files (yamanote, asakusa, ginza, marunouchi, hibiya, tozai, chiyoda, yurakucho, hanzomon, namboku, fukutoshin, mita, shinjuku, oedo). "shinjuku" already exists as the Toei subway line — these JR keys are all distinct.`,
  { label: `jr:${L.key}`, phase: '生成 JR 線資料', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      key: { type: 'string' }, file: { type: 'string' },
      symbol: { type: 'string' }, station_count: { type: 'number' },
      json_valid: { type: 'boolean' }, notes: { type: 'string' },
    },
    required: ['key', 'file', 'station_count', 'json_valid'],
  } }
)))

const ok = results.filter(Boolean)
log(`generated JR: ${ok.map(r => `${r.key}/${r.symbol}(${r.station_count})`).join(', ')}`)

phase('驗證')
const verify = await agent(
  `Verify the jrboard engine handles the new JR lines. Package at ${PKG}; data/ now has the original 14 lines plus new JR files (chuo, sobu, keihintohoku, saikyo, shonanshinjuku, yokosuka).\n` +
  `Run and paste real output as evidence:\n` +
  `1. python3 ${PROJECT}/main.py --list   — must list EVERY line incl. the new JR ones with station counts.\n` +
  `2. For 3 new JR lines (e.g. chuo, sobu, keihintohoku) pick a real station and run:\n` +
  `   python3 ${PROJECT}/main.py --once --line <key> --station <station> --no-flap\n` +
  `   Confirm board renders, CJK columns align (every border row 60 cols), neighbours/colours correct.\n` +
  `3. python3 ${PROJECT}/main.py --mode statusline --line sobu --station akihabara --columns 70\n` +
  `4. Validate every data/*.json parses.\n` +
  `If a file is malformed or a station key fails, FIX the data file (do not change engine code unless there is a real engine bug). Report what you ran and any fixes.`,
  { label: 'verify-jr-lines', phase: '驗證', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      lines_listed: { type: 'array', items: { type: 'string' } },
      commands_run: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, ok: { type: 'boolean' }, output_excerpt: { type: 'string' } }, required: ['cmd', 'ok'] } },
      fixes: { type: 'array', items: { type: 'string' } },
      all_json_valid: { type: 'boolean' },
      total_lines: { type: 'number' },
      summary: { type: 'string' },
    },
    required: ['lines_listed', 'commands_run', 'all_json_valid', 'summary'],
  } }
)

return {
  generated: ok.map(r => ({ key: r.key, symbol: r.symbol, stations: r.station_count, valid: r.json_valid })),
  failed: LINES.length - ok.length,
  verify,
}
