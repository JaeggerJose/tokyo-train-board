export const meta = {
  name: 'jr-board-expand-lines',
  description: 'Generate JSON data files for all Tokyo Metro (9) + remaining Toei (3) subway lines following the fixed data contract, then verify the engine lists/renders them',
  phases: [
    { title: '生成線路資料', detail: 'one agent per line writes data/<key>.json' },
    { title: '驗證', detail: 'engine lists all lines and renders samples' },
  ],
}

const PROJECT = '/Users/minghsuan/Downloads/JR-timetable'
const PKG = `${PROJECT}/jrboard`

const DATA_CONTRACT = `
Write ONE JSON file at ${PKG}/data/<key>.json with this exact schema (no comments in the real file):
{
  "key": "<lowercase file basename>",
  "name_jp": "...", "name_en": "...",
  "symbol": "<line letter code shown in the station-number badge>",
  "color": { "name": "...", "ansi_fg": "\\u001b[38;5;<n>m", "ansi_bg": "\\u001b[48;5;<n>m\\u001b[38;5;<fg>m", "hex": "#RRGGBB" },
  "operator": "TokyoMetro" | "Toei",
  "odpt_railway": "odpt.Railway:<Operator>.<Line>",
  "loop": false,
  "stations": [
    { "id": "<symbol+number e.g. G01>", "number": "01", "name_jp": "...", "kana": "<hiragana>", "name_en": "<official Hepburn>", "odpt_station": "odpt.Station:<Operator>.<Line>.<RomajiNoSpaces>" }
    // ALL real stations, real running order
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
- Stations MUST be the REAL stations in REAL order. kana = hiragana reading. name_en = official Hepburn (hyphenate compounds like Naka-meguro, Nishi-funabashi).
- color.hex MUST be the official line color; pick the closest xterm-256 code for ansi_fg/ansi_bg, with a readable contrasting foreground in ansi_bg.
- headway_min realistic for THAT line (rush hours denser). directions = the two real termini.
- Validate JSON parses before finishing.
- Return a short confirmation only; do NOT dump file contents.
`

// Each entry: file key + the line-specific facts the agent must encode.
const LINES = [
  { key: 'ginza',      desc: '東京メトロ銀座線 (Tokyo Metro Ginza Line). symbol "G", operator TokyoMetro, odpt.Railway:TokyoMetro.Ginza. Official color orange #FF9500. 19 stations, 浅草(G19)↔渋谷(G01) — confirm number direction. Termini: 浅草方面 / 渋谷方面.' },
  { key: 'marunouchi', desc: '東京メトロ丸ノ内線 (Marunouchi Line) MAIN line only. symbol "M", operator TokyoMetro, odpt.Railway:TokyoMetro.Marunouchi. Official color red #F62E36. ~25 stations 池袋(M25)↔荻窪(M01). (Skip the 中野坂上–方南町 branch.) Termini: 池袋方面 / 荻窪方面.' },
  { key: 'hibiya',     desc: '東京メトロ日比谷線 (Hibiya Line). symbol "H", operator TokyoMetro, odpt.Railway:TokyoMetro.Hibiya. Official color silver/grey #B5B5AC. 22 stations 北千住(H22)↔中目黒(H01). Termini: 北千住方面 / 中目黒方面.' },
  { key: 'tozai',      desc: '東京メトロ東西線 (Tozai Line). symbol "T", operator TokyoMetro, odpt.Railway:TokyoMetro.Tozai. Official color sky blue #009BBF. 23 stations 中野(T01)↔西船橋(T23). Termini: 中野方面 / 西船橋方面.' },
  { key: 'chiyoda',    desc: '東京メトロ千代田線 (Chiyoda Line) MAIN. symbol "C", operator TokyoMetro, odpt.Railway:TokyoMetro.Chiyoda. Official color green #00BB85. 20 stations 代々木上原(C01)↔綾瀬(C20). (Skip 綾瀬–北綾瀬 branch.) Termini: 代々木上原方面 / 綾瀬方面.' },
  { key: 'yurakucho',  desc: '東京メトロ有楽町線 (Yurakucho Line). symbol "Y", operator TokyoMetro, odpt.Railway:TokyoMetro.Yurakucho. Official color gold #C1A470. 24 stations 和光市(Y01)↔新木場(Y24). Termini: 和光市方面 / 新木場方面.' },
  { key: 'hanzomon',   desc: '東京メトロ半蔵門線 (Hanzomon Line). symbol "Z", operator TokyoMetro, odpt.Railway:TokyoMetro.Hanzomon. Official color purple #8F76D6. 14 stations 渋谷(Z01)↔押上(Z14). Termini: 渋谷方面 / 押上方面.' },
  { key: 'namboku',    desc: '東京メトロ南北線 (Namboku Line). symbol "N", operator TokyoMetro, odpt.Railway:TokyoMetro.Namboku. Official color emerald/teal #00AC9B. 19 stations 目黒(N01)↔赤羽岩淵(N19). Termini: 目黒方面 / 赤羽岩淵方面.' },
  { key: 'fukutoshin', desc: '東京メトロ副都心線 (Fukutoshin Line). symbol "F", operator TokyoMetro, odpt.Railway:TokyoMetro.Fukutoshin. Official color brown #9C5E31. 16 stations 和光市(F01)↔渋谷(F16). Termini: 和光市方面 / 渋谷方面.' },
  { key: 'mita',       desc: '都営三田線 (Toei Mita Line). symbol "I", operator Toei, odpt.Railway:Toei.Mita. Official color blue #0079C2. ~27 stations 目黒(I01)↔西高島平(I27). Termini: 目黒方面 / 西高島平方面.' },
  { key: 'shinjuku',   desc: '都営新宿線 (Toei Shinjuku Line). symbol "S", operator Toei, odpt.Railway:Toei.Shinjuku. Official color leaf green #6CBB5A. 21 stations 新宿(S01)↔本八幡(S21). Termini: 新宿方面 / 本八幡方面. NOTE key is "shinjuku" — this is the Toei Shinjuku subway line, NOT JR.' },
  { key: 'oedo',       desc: '都営大江戸線 (Toei Oedo Line). symbol "E", operator Toei, odpt.Railway:Toei.Oedo. Official color magenta #B6007A. ~38 stations; it is a loop-with-tail: 光が丘(E28)→...→都庁前(E28? ) forms a 6-shape ending at 都庁前. Encode stations in service order from 光が丘 through the loop back to 都庁前; set loop=false (the tail makes it non-circular). Termini: 光が丘方面 / 都庁前方面.' },
]

phase('生成線路資料')
const results = await parallel(LINES.map(L => () => agent(
  `Gather REAL data and WRITE the file ${PKG}/data/${L.key}.json. Accuracy matters — this is real transit data.\n\n` +
  `Line: ${L.desc}\n\n` +
  `Follow this contract EXACTLY:\n${DATA_CONTRACT}\n\n` +
  `Sources: Wikipedia line article + official operator station list for the order/readings/Hepburn. Cross-check the station COUNT matches. Create ${PKG}/data if missing.`,
  { label: `line:${L.key}`, phase: '生成線路資料', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      key: { type: 'string' }, file: { type: 'string' },
      station_count: { type: 'number' }, json_valid: { type: 'boolean' }, notes: { type: 'string' },
    },
    required: ['key', 'file', 'station_count', 'json_valid'],
  } }
)))

const ok = results.filter(Boolean)
log(`generated: ${ok.map(r => `${r.key}(${r.station_count})`).join(', ')}`)

phase('驗證')
const verify = await agent(
  `Verify the jrboard engine handles ALL the new lines. The package is at ${PKG}; data/ now holds many <key>.json files (yamanote, asakusa + the new Tokyo Metro & Toei lines).\n` +
  `Run and paste real output as evidence:\n` +
  `1. python3 ${PROJECT}/main.py --list   — must list EVERY line with its station count.\n` +
  `2. For 3 different new lines (e.g. ginza, oedo, tozai), pick a real station on each and run:\n` +
  `   python3 ${PROJECT}/main.py --once --line <key> --station <station> --no-flap\n` +
  `   Confirm the board renders, CJK columns align, and neighbors/colors are correct.\n` +
  `3. python3 ${PROJECT}/main.py --mode statusline --line oedo --station tochomae\n` +
  `4. Validate every data/*.json parses (python3 -c "import json,glob;[json.load(open(f)) for f in glob.glob('${PKG}/data/*.json')]").\n` +
  `If any line file is malformed or a station key fails, FIX the data file (do not change engine code unless there is a real engine bug). Report exactly what you ran and any fixes.`,
  { label: 'verify-all-lines', phase: '驗證', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      lines_listed: { type: 'array', items: { type: 'string' } },
      commands_run: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, ok: { type: 'boolean' }, output_excerpt: { type: 'string' } }, required: ['cmd', 'ok'] } },
      fixes: { type: 'array', items: { type: 'string' } },
      all_json_valid: { type: 'boolean' },
      summary: { type: 'string' },
    },
    required: ['lines_listed', 'commands_run', 'all_json_valid', 'summary'],
  } }
)

return {
  generated: ok.map(r => ({ key: r.key, stations: r.station_count, valid: r.json_valid })),
  failed: LINES.length - ok.length,
  verify,
}
