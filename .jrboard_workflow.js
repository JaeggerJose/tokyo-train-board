export const meta = {
  name: 'jr-board-rebuild',
  description: 'Rebuild JR timetable board: real ODPT data + static fallback, line/station switching (Yamanote/Asakusa), split-flap animation, single-line statusline marquee',
  phases: [
    { title: '研究與資料', detail: 'ODPT API specifics + gather real station/timetable data' },
    { title: '實作模組', detail: 'parallel build of disjoint modules' },
    { title: '整合與除錯', detail: 'wire cli/main, run, debug, test, verify' },
  ],
}

const PROJECT = '/Users/minghsuan/Downloads/JR-timetable'
const PKG = `${PROJECT}/jrboard`

// ---- Fixed data contract: both the data-writer agent and the model agent follow this exactly ----
const DATA_CONTRACT = `
Each line is one JSON file at ${PKG}/data/<key>.json with this exact schema:
{
  "key": "yamanote",                         // file basename, lowercase
  "name_jp": "山手線",
  "name_en": "Yamanote Line",
  "symbol": "JY",                            // line code shown in the station-number badge
  "color": { "name": "yellow-green", "ansi_fg": "\\u001b[38;5;148m", "ansi_bg": "\\u001b[48;5;148m\\u001b[38;5;232m", "hex": "#9ACD32" },
  "operator": "JR-East",                     // or "Toei"
  "odpt_railway": "odpt.Railway:JR-East.Yamanote",
  "loop": true,                              // Yamanote is a loop line; Asakusa is not
  "stations": [
    {
      "id": "JY01", "number": "01",
      "name_jp": "東京", "kana": "とうきょう", "name_en": "Tokyo",
      "odpt_station": "odpt.Station:JR-East.Yamanote.Tokyo"
    }
    // ... ALL real stations in correct running order
  ],
  "timetable": {
    "first_train": "04:26",
    "last_train": "01:18",
    "headway_min": {                          // typical minutes between trains by hour-of-day, realistic values
      "weekday": { "5": 10, "6": 6, "7": 4, "8": 3, "9": 4, "10": 5, "11": 5, "12": 5, "13": 5, "14": 5, "15": 5, "16": 5, "17": 4, "18": 3, "19": 4, "20": 5, "21": 5, "22": 6, "23": 7, "0": 10, "1": 12 },
      "holiday": { "5": 12, "6": 8, "7": 6, "8": 5, "9": 5, "10": 5, "11": 5, "12": 5, "13": 5, "14": 5, "15": 5, "16": 5, "17": 5, "18": 5, "19": 6, "20": 6, "21": 7, "22": 8, "23": 9, "0": 12, "1": 14 }
    },
    "directions": [
      { "id": "outer", "name_jp": "外回り", "via_jp": "品川・渋谷方面", "track": "1" },
      { "id": "inner", "name_jp": "内回り", "via_jp": "上野・池袋方面", "track": "2" }
    ]
  }
}
RULES:
- Station names MUST be the REAL stations of the line, in the REAL running order. Yamanote = 30 stations. Toei Asakusa = 20 stations.
- kana = hiragana reading; name_en = official Hepburn romanization (e.g. "Shinjuku", "Shin-Okubo", "Nishi-magome").
- For Asakusa line use symbol "A", operator "Toei", odpt_railway "odpt.Railway:Toei.Asakusa", loop=false, station ids like "A01".. and odpt_station "odpt.Station:Toei.Asakusa.Nishimagome". Directions: 西馬込方面 (track varies, use "1") and 押上方面 ("2"). Asakusa through-services to Keisei/Keikyu — keep via_jp simple and realistic.
- headway values must be realistic for that line (Asakusa is less frequent than Yamanote).
- Output valid JSON (no comments in the actual file). UTF-8.
`

// ---- Fixed module interfaces: every implementation agent codes to these signatures ----
const INTERFACES = `
Python package at ${PKG}. Python 3, PEP8, type hints on all signatures, frozen dataclasses for value objects, files < 300 lines, no print() for logging (use sys.stderr), comprehensive error handling, no mutation.

jrboard/width.py
  def get_visual_width(text: str) -> int        # strips ANSI (\\033[...m) then counts CJK wide chars (east_asian_width W/F) as 2
  def safe_pad(text: str, target_w: int, align: str = 'left') -> str   # pads to EXACT visual width; align in {'left','right','center'}; if already wider, return unchanged

jrboard/model.py   (reads JSON files per the DATA CONTRACT)
  @dataclass(frozen=True) class Station: id:str; number:str; name_jp:str; kana:str; name_en:str; odpt_station:str
  @dataclass(frozen=True) class Direction: id:str; name_jp:str; via_jp:str; track:str
  @dataclass(frozen=True) class Line:
      key:str; name_jp:str; name_en:str; symbol:str; operator:str; odpt_railway:str; loop:bool
      ansi_fg:str; ansi_bg:str; hex:str
      stations: tuple[Station, ...]
      first_train:str; last_train:str; headway_min:dict; directions: tuple[Direction, ...]
  def data_dir() -> str                         # absolute path to jrboard/data
  def available_lines() -> list[str]            # keys of json files present
  def load_line(key: str) -> Line               # raises ValueError on unknown key with helpful message listing available
  def find_station(line: Line, station_key: str) -> Station   # match by lowercased name_en or id or number; ValueError if none
  def neighbors(line: Line, station: Station) -> tuple[Station|None, Station, Station|None]  # prev,curr,next; wraps around when line.loop

jrboard/sources.py  (repository pattern; depends on model.Line/Station)
  @dataclass(frozen=True) class Departure: time:str ("HH:MM"); kind_jp:str (種別 e.g. 各駅停車); dest_jp:str (行先/方面); track:str (番線); direction:str (direction id)
  class TimetableSource(Protocol): def departures(self, line, station, now, limit) -> list[Departure]: ...
  class ODPTSource:   # uses env ODPT_KEY; hits ODPT v4 StationTimetable; parse into Departure; raise on any failure (no key, http error, empty)
  class StaticSource: # generates realistic Departure list from line.timetable headway for current hour + both directions, sorted by time, future-only relative to now
  def get_departures(line, station, now, limit: int = 6) -> tuple[list[Departure], str]
      # returns (departures, source_label) where source_label is "ODPT" or "STATIC"; tries ODPTSource only if os.environ.get('ODPT_KEY'); on failure logs to stderr and falls back to StaticSource

jrboard/flap.py    (PURE, no I/O — split-flap / Solari board engine)
  FLAP_POOL_LATIN, FLAP_POOL_KANA, FLAP_POOL_DIGITS constants (scramble character pools)
  def lock_threshold(index: int, total: int, jitter_seed: int) -> float
      # returns a value in [0,1): the progress fraction at which character at position 'index' locks to its target.
      # default: left-to-right wipe with small deterministic jitter. THIS IS THE TUNABLE EASING CURVE.
  def scramble_line(target: str, progress: float, seed: int) -> str
      # returns a string with the SAME visual width as target; each char position shows the real char if lock_threshold<=progress else a random pool char chosen per (seed,index,progress-bucket). Spaces and ANSI sequences pass through untouched.
  def flap_frames(targets: list[str], steps: int = 12, seed: int = 0) -> Iterator[list[str]]
      # yields successive frames (each a list[str] same length as targets) from full scramble to fully resolved (last frame == targets)

jrboard/render.py   (depends on width, model, sources; ANSI board like the original yamanote_board.py screenshot)
  def render_station_sign(line: Line, station: Station, width: int = 60) -> list[str]   # returns list of text lines (with ANSI) — the station nameplate (number badge, big JP name, kana+EN, green nav bar prev/curr/next JP, EN row)
  def render_timetable(line: Line, departures: list[Departure], width: int = 60, source_label: str = "STATIC") -> list[str]
  def render_board(line, station, departures, width=60, source_label="STATIC") -> list[str]   # sign + timetable combined
  # Keep the visual style of the existing yamanote_board.py (box drawing +---+, green bar) but driven by the Line's color and the real station/neighbor names. Show source_label (ODPT/STATIC) discreetly.

jrboard/statusline.py  (single-line marquee for Claude Code statusLine)
  def statusline_text(line, station, departures, now, columns: int = 0) -> str
      # ONE line, no trailing newline. Compact: line symbol badge + station + ' ▸ ' + next 2-3 departures "HH:MM 方面".
      # MARQUEE: if the content is wider than 'columns' (when columns>0), scroll it horizontally; the scroll offset is derived from now (e.g. seconds) so successive invocations advance it. Use width.get_visual_width for correct CJK handling. Keep ANSI minimal/optional so it is safe in a statusline.
`

phase('研究與資料')
const research = await parallel([
  () => agent(
    `Research the ODPT (Open Data Platform for Transportation, odpt.org) API v4 so we can integrate it.\n` +
    `Use WebSearch/WebFetch (via ToolSearch) against developer.odpt.org / api.odpt.org docs. Confirm the EXACT, CURRENT details — do not guess:\n` +
    `- base URL and the StationTimetable endpoint path\n` +
    `- the consumer-key query parameter name\n` +
    `- the railway id strings for JR-East Yamanote and Toei Asakusa\n` +
    `- the station id format/examples\n` +
    `- the JSON fields inside a StationTimetable object and inside each stationTimetableObject entry (departure time, destination, train type, platform if any)\n` +
    `- the URL where a developer signs up for a free consumer key\n` +
    `- whether JR-East data needs the ODPT Challenge endpoint vs the standard one, and any realtime-train-info caveats\n` +
    `Return findings as structured data. If a fact cannot be confirmed from docs, mark it confidence:"low".`,
    { label: 'research:odpt', phase: '研究與資料', schema: {
      type: 'object', additionalProperties: true,
      properties: {
        base_url: { type: 'string' },
        consumer_key_param: { type: 'string' },
        station_timetable_endpoint: { type: 'string' },
        railway_ids: { type: 'object', properties: { yamanote: { type: 'string' }, asakusa: { type: 'string' } }, required: ['yamanote','asakusa'] },
        station_id_examples: { type: 'array', items: { type: 'string' } },
        timetable_object_fields: { type: 'array', items: { type: 'string' } },
        departure_entry_fields: { type: 'array', items: { type: 'string' } },
        signup_url: { type: 'string' },
        jr_east_notes: { type: 'string' },
        confidence: { type: 'string' },
      },
      required: ['base_url','consumer_key_param','station_timetable_endpoint','railway_ids','signup_url'],
    } }
  ),
  () => agent(
    `Gather REAL data for two rail lines and WRITE two JSON files using the Write tool. THIS FIXES the "data is fake" problem, so accuracy matters.\n\n` +
    `Files to write:\n- ${PKG}/data/yamanote.json  (JR-East 山手線, 30 stations, loop line)\n- ${PKG}/data/asakusa.json  (Toei 都営浅草線, 20 stations, not a loop)\n\n` +
    `Follow this contract EXACTLY:\n${DATA_CONTRACT}\n\n` +
    `Get the real station list, order, hiragana readings, and official English (Hepburn) names from authoritative sources (Wikipedia line articles / official operator pages). Yamanote canonical order starts 東京→神田→秋葉原→... For Toei Asakusa: 西馬込(A01)→...→押上(A20).\n` +
    `Create the ${PKG}/data directory first (mkdir -p). Validate each file parses as JSON before finishing (python -c "import json,glob; [json.load(open(f)) for f in glob.glob('${PKG}/data/*.json')]").\n` +
    `Return a short confirmation only — do NOT dump the file contents.`,
    { label: 'data:stations', phase: '研究與資料', schema: {
      type: 'object', additionalProperties: false,
      properties: {
        files_written: { type: 'array', items: { type: 'string' } },
        station_counts: { type: 'object', additionalProperties: { type: 'number' } },
        json_valid: { type: 'boolean' },
        notes: { type: 'string' },
      },
      required: ['files_written','station_counts','json_valid'],
    } }
  ),
])
const odpt = research[0]
const dataReport = research[1]
log(`ODPT confidence=${odpt?.confidence ?? 'n/a'}; data files=${JSON.stringify(dataReport?.station_counts ?? {})}`)

const ODPT_FACTS = JSON.stringify(odpt ?? {}, null, 0)

phase('實作模組')
const MOD = (name, extra) => agent(
  `Implement ${name} in the jrboard package. Follow these interfaces EXACTLY (signatures and behavior):\n${INTERFACES}\n\n` +
  `Confirmed ODPT API facts (use for sources.py if relevant): ${ODPT_FACTS}\n\n` +
  `Data files already exist at ${PKG}/data/*.json per this contract:\n${DATA_CONTRACT}\n\n` +
  `Write ONLY the file(s) assigned to you with the Write tool: ${name}. Do NOT create __init__.py, cli.py, or main.py (a later step owns those). Do NOT modify other modules. ${extra ?? ''}\n` +
  `Make it import-safe in isolation as much as possible. Return your file path, exported names, and any assumptions.`,
  { label: `impl:${name}`, phase: '實作模組', schema: {
    type: 'object', additionalProperties: false,
    properties: { file: { type: 'string' }, exports: { type: 'array', items: { type: 'string' } }, status: { type: 'string' }, notes: { type: 'string' } },
    required: ['file','status'],
  } }
)

const impls = await parallel([
  () => MOD('width.py and model.py', 'model.py reads the JSON data files. Use east_asian_width for width. find_station should be forgiving (case-insensitive, match name_en/id/number).'),
  () => MOD('sources.py', 'StaticSource must produce a believable upcoming-departures list from headway_min for the current hour and BOTH directions, future-relative-to-now, sorted, limited. ODPTSource reads ODPT_KEY env; on ANY problem raise so get_departures falls back. Use stdlib only except `requests` (already a dep per test.py).'),
  () => MOD('flap.py', 'Pure functions only, deterministic given seed (no Math.random equivalent surprises — use Python random.Random(seed)). scramble_line MUST preserve visual width and never split a multibyte char. lock_threshold is the tunable easing curve — implement a sensible left-to-right wipe with mild jitter and document it clearly.'),
  () => MOD('render.py', 'Mirror the visual style of the existing /Users/minghsuan/Downloads/JR-timetable/yamanote_board.py (read it for reference) but generalized over Line/Station/neighbors and real data. Return list[str]; do not print. Drive colors from line.ansi_bg/ansi_fg.'),
  () => MOD('statusline.py', 'Single line, marquee scroll derived from now. Must be safe to embed in a shell statusline. Provide minimal-ANSI output.'),
])
log(`modules: ${impls.filter(Boolean).map(m => m.file).join(', ')}`)

phase('整合與除錯')
const integration = await agent(
  `Integrate and DEBUG the jrboard package into a working program. The package dir is ${PKG} and already contains: data/*.json, width.py, model.py, sources.py, flap.py, render.py, statusline.py.\n\n` +
  `Interfaces (the contract every module followed):\n${INTERFACES}\n\n` +
  `Your tasks:\n` +
  `1. Create ${PKG}/__init__.py (can be minimal, export nothing heavy).\n` +
  `2. Create ${PKG}/cli.py with argparse:\n` +
  `   --line {yamanote,asakusa} (default yamanote), --station <key> (default a sensible flagship like shinjuku for yamanote, asakusa for asakusa),\n` +
  `   --mode {board,statusline} (default board), --no-flap, --once (render once and exit), --interval <sec> (default 10), --list (print available lines+stations and exit), --width <int> (default 60).\n` +
  `   board mode: clear screen, run flap_frames animation into the resolved board, hold, then refresh on interval. statusline mode: print exactly one line and exit (so a Claude Code statusLine command can call it each render; marquee advances via current time).\n` +
  `3. Create ${PROJECT}/main.py as a thin entry: \`from jrboard.cli import main\` then \`main()\`.\n` +
  `4. RUN and DEBUG until these all work (paste real output as evidence):\n` +
  `   - python3 ${PROJECT}/main.py --list\n` +
  `   - python3 ${PROJECT}/main.py --mode statusline --line yamanote --station shinjuku --once   (or just statusline mode)\n` +
  `   - python3 ${PROJECT}/main.py --mode statusline --line asakusa --station asakusa\n` +
  `   - python3 ${PROJECT}/main.py --once --line yamanote --station shinjuku   (board renders fully, flap resolves to real data)\n` +
  `   - python3 ${PROJECT}/main.py --once --line asakusa --station oshiage --no-flap\n` +
  `   Fix every traceback. Verify CJK alignment columns line up. Verify fallback prints a STATIC source label when ODPT_KEY is unset.\n` +
  `5. Write pytest tests in ${PROJECT}/tests/ for: width (CJK + ANSI), model (load_line, find_station, neighbors incl. loop wrap), sources (StaticSource future/sorted/limit; get_departures falls back to STATIC when no key), flap (scramble_line preserves visual width; final flap_frames frame equals targets). Run \`python3 -m pytest ${PROJECT}/tests -q\` and make them pass.\n` +
  `Return a structured report with the exact commands run and short output excerpts proving each works.`,
  { label: 'integrate+debug', phase: '整合與除錯', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      created_files: { type: 'array', items: { type: 'string' } },
      commands_run: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, ok: { type: 'boolean' }, output_excerpt: { type: 'string' } }, required: ['cmd','ok'] } },
      bugs_fixed: { type: 'array', items: { type: 'string' } },
      tests_passing: { type: 'boolean' },
      test_summary: { type: 'string' },
      statusline_sample: { type: 'string' },
      summary: { type: 'string' },
    },
    required: ['created_files','commands_run','tests_passing','summary'],
  } }
)

return {
  odpt_confidence: odpt?.confidence ?? 'n/a',
  data_report: dataReport,
  modules: impls.filter(Boolean).map(m => ({ file: m.file, status: m.status })),
  integration,
}
