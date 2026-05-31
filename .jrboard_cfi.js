export const meta = {
  name: 'jr-board-cfi',
  description: 'Build interactive TUI (C), engineering/packaging + CI + config + golden tests (F), and productivity modes — pomodoro-journey / commute / ICS agenda (I)',
  phases: [
    { title: '基礎建設', detail: 'config.py + pyproject + CI + golden tests (no cli edits)' },
    { title: '功能模組', detail: 'parallel disjoint modules: tui, journey, commute, ics feed' },
    { title: '整合除錯', detail: 'wire cli + README, run, debug, full test sweep' },
  ],
}

const PROJECT = '/Users/minghsuan/Downloads/JR-timetable'
const PKG = `${PROJECT}/jrboard`

// ---- Recap of EXISTING engine interfaces (agents must reuse, not reinvent) ----
const ENGINE = `
EXISTING package at ${PKG} (Python 3.11+, PEP8, type hints, frozen dataclasses, small files, errors handled, no mutation). Reuse these — DO NOT reimplement:
- jrboard/width.py:     get_visual_width(text)->int ; safe_pad(text,target_w,align='left')->str
- jrboard/model.py:     Station(id,number,name_jp,kana,name_en,odpt_station) ; Direction(...) ;
                        Line(key,name_jp,name_en,symbol,operator,odpt_railway,loop,ansi_fg,ansi_bg,hex,stations,first_train,last_train,headway_min,directions)
                        available_lines()->list[str] ; load_line(key)->Line ; find_station(line,key)->Station ;
                        neighbors(line,station)->(prev|None,curr,next|None)
- jrboard/sources.py:   Departure(time:'HH:MM',kind_jp,dest_jp,track,direction) ;
                        get_departures(line,station,now,limit=6)->(list[Departure], source_label:str)  # 'ODPT'|'STATIC'
- jrboard/render.py:    render_station_sign(line,station,width=60)->list[str] ;
                        render_timetable(line,departures,width=60,source_label='STATIC')->list[str] ;
                        render_board(line,station,departures,width=60,source_label='STATIC')->list[str]
- jrboard/flap.py:      flap_frames(targets:list[str],steps=22,seed=0)->Iterator[list[str]]
- jrboard/statusline.py: statusline_text(line,station,departures,now,columns=0,pin_label=True,color=True)->str
- jrboard/cli.py:       main()->int   # DO NOT EDIT in phase 2; only the integration phase edits cli.py
`

// ---- Fixed contract for the config module (phase 1), consumed by phase 2 modules ----
const CONFIG_CONTRACT = `
jrboard/config.py  (read ~/.config/jrboard/config.toml via stdlib tomllib; NEVER raise — return defaults if missing/malformed, log to stderr):
  @dataclass(frozen=True) class Config:
      line: str = 'yamanote'
      station: str = 'shinjuku'
      columns: int = 50
      width: int = 60
      flap_steps: int = 22
      flap_delay: float = 0.08
      pin_label: bool = True
      color: bool = True
      home: tuple[str, str] | None = None      # (line_key, station_key)
      work: tuple[str, str] | None = None       # (line_key, station_key)
      leave_buffer_min: int = 5                  # walk-to-station buffer for commute guardian
  def config_path() -> str                       # ~/.config/jrboard/config.toml (respect XDG_CONFIG_HOME)
  def load_config() -> Config                    # parse toml [board]/[commute] sections; defaults on any error
  def favorites_path() -> str                    # ~/.config/jrboard/favorites.txt
  def load_favorites() -> list[tuple[str, str]]  # each line "line_key,station_key"; [] if none
  def save_favorites(favs: list[tuple[str, str]]) -> None   # write favorites.txt atomically; create dir
Example config.toml the loader must accept:
  [board]
  line = "oedo"
  station = "tochomae"
  columns = 50
  [commute]
  home = ["yamanote", "shinjuku"]
  work = ["yamanote", "tokyo"]
  leave_buffer_min = 7
`

phase('基礎建設')
const foundation = await agent(
  `Build the engineering/packaging foundation for the jrboard project. ${ENGINE}\n\n` +
  `Create these files with the Write tool. DO NOT edit cli.py or any existing module.\n\n` +
  `1. ${PKG}/config.py — exactly this contract:\n${CONFIG_CONTRACT}\n` +
  `   Use stdlib tomllib (Python 3.11+). Be defensive: missing file/section/key => documented default. Coerce types. home/work parsed from 2-element arrays.\n\n` +
  `2. ${PROJECT}/pyproject.toml — setuptools build; package = jrboard (include jrboard/data/*.json as package data); requires-python = ">=3.11"; optional dependency group [project.optional-dependencies] live = ["requests"]; console entry point: [project.scripts] jrboard = "jrboard.cli:main". Project name "tokyo-train-board", version 0.1.0, MIT, description, readme = README.md.\n\n` +
  `3. ${PROJECT}/.github/workflows/ci.yml — GitHub Actions: on push/PR; matrix python 3.11/3.12/3.13; steps: checkout, setup-python, pip install -e ".[live]" pytest, run \`python -m pytest -q\`.\n\n` +
  `4. ${PROJECT}/tests/test_config.py — test load_config defaults when no file, parsing a written temp config (monkeypatch XDG_CONFIG_HOME to tmp_path), favorites round-trip (save then load).\n\n` +
  `5. ${PROJECT}/tests/test_render_golden.py + ${PROJECT}/tests/golden/*.txt — DETERMINISTIC golden snapshot tests. Render render_board for 3 representative lines (yamanote/shinjuku, ginza/ginza, oedo/tochomae) at a FIXED datetime (e.g. datetime(2026,5,31,8,0,0)) with ANSI stripped, assert equals committed golden file; provide an env JRBOARD_UPDATE_GOLDEN=1 path to regenerate. Generate the golden files now by running the render and writing the stripped output. Also assert every row width == expected via get_visual_width.\n\n` +
  `Run \`python3 -m pytest ${PROJECT}/tests -q\` and make everything pass. Return the config.py public API you implemented and files created.`,
  { label: 'F:foundation', phase: '基礎建設', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      files: { type: 'array', items: { type: 'string' } },
      config_api: { type: 'array', items: { type: 'string' } },
      tests_passing: { type: 'boolean' },
      notes: { type: 'string' },
    },
    required: ['files', 'tests_passing'],
  } }
)
log(`foundation: ${(foundation?.files || []).length} files, tests_passing=${foundation?.tests_passing}`)

phase('功能模組')
const COMMON = `${ENGINE}\n\nThe config module now exists:\n${CONFIG_CONTRACT}\n\nWrite ONLY your assigned file(s). DO NOT edit cli.py or other modules. Make functions pure/testable where possible; keep curses/IO at the edges. Add a matching tests/ file. PEP8 + type hints. Return file path, public functions, and how the integration step should call you.`

const modules = await parallel([
  // C — interactive TUI
  () => agent(
    `Implement an interactive terminal UI. ${COMMON}\n\n` +
    `File: ${PKG}/tui.py\n` +
    `def run_tui(line_key: str | None = None, station_key: str | None = None, config=None) -> int\n` +
    `Use the stdlib 'curses' module (NO external deps). Layout: left pane = scrollable line list (all available_lines(), showing symbol + name_jp in each line's colour); right pane = the live board (render_board) for the selected line+station.\n` +
    `Keys: ↑/↓ or j/k move selection; ←/→ or h/l change the station along the line (neighbors order); Enter select line; '/' fuzzy-filter the line list by typed text; 'f' toggle favourite (persist via config.save_favorites); 'F' jump among favourites; 'r' refresh; 'q' quit.\n` +
    `Re-render the board periodically (e.g. every 1s via curses timeout) so departures stay current. Handle terminal resize and tiny terminals gracefully. Strip/という ANSI is NOT needed inside curses if you use curses colour, BUT simplest: render_board returns ANSI strings — for curses, render the board with ANSI stripped and print plainly (use a helper to strip ESC sequences), OR addstr the plain text. Keep it robust over pretty.\n` +
    `Factor the non-curses logic (filtering the line list, computing the next/prev station, favourite toggle) into PURE functions so they are unit-testable without a TTY. tests/test_tui.py covers those pure helpers (fuzzy filter, station stepping with loop wrap, favourite toggle).`,
    { label: 'C:tui', phase: '功能模組', schema: { type: 'object', additionalProperties: false, properties: { file: { type: 'string' }, functions: { type: 'array', items: { type: 'string' } }, integration_hint: { type: 'string' }, notes: { type: 'string' } }, required: ['file'] } }
  ),
  // I-1 — pomodoro train journey
  () => agent(
    `Implement a "pomodoro as a train journey" mode (pure logic + renderer). ${COMMON}\n\n` +
    `File: ${PKG}/journey.py\n` +
    `@dataclass(frozen=True) class Journey: line: Line; origin: Station; dest: Station; start_epoch: float; duration_sec: int\n` +
    `def make_journey(line, origin, dest, start_epoch, duration_min) -> Journey\n` +
    `def progress(journey, now_epoch) -> float   # clamped 0..1\n` +
    `def remaining_sec(journey, now_epoch) -> int\n` +
    `def render_journey(journey, now_epoch, width: int = 60) -> list[str]   # a board: header '集中タイマー', an ASCII line from origin→dest with the train ▶ positioned by progress, the destination, big remaining 'あと N 分', arrival clock, and a progress bar. Reuse width.safe_pad + line colour. Pure (no sleeping/printing).\n` +
    `Idea: pick origin/dest as two real stations on the chosen line spaced ~ proportional to duration, or just label origin='いま' dest='集中' if no station pair given. tests/test_journey.py: progress 0 at start, 1 at/after end, monotonic; remaining_sec correct; render rows all == width visual cols; final frame shows arrival.`,
    { label: 'I:journey', phase: '功能模組', schema: { type: 'object', additionalProperties: false, properties: { file: { type: 'string' }, functions: { type: 'array', items: { type: 'string' } }, integration_hint: { type: 'string' }, notes: { type: 'string' } }, required: ['file'] } }
  ),
  // I-2 — commute guardian
  () => agent(
    `Implement a commute guardian (pure logic). ${COMMON}\n\n` +
    `File: ${PKG}/commute.py\n` +
    `Given config.home/work (line_key, station_key) and the current time, figure out the relevant direction (home->work in the morning, work->home in the evening; threshold ~ before/after 14:00 local, but make it a small helper you can test), get upcoming departures via get_departures, and compute when the user must LEAVE to catch each of the next few trains, accounting for config.leave_buffer_min walking time.\n` +
    `@dataclass(frozen=True) class CommuteAdvice: line: Line; station: Station; heading: str; trains: list[Departure]; leave_in_min: int   # minutes until you must leave for the soonest catchable train\n` +
    `def commute_advice(config, now) -> CommuteAdvice | None   # None if home/work not configured\n` +
    `def render_commute(advice, now, width: int = 60) -> list[str]   # board: 'I need to leave in N min' headline + next trains; colour by line\n` +
    `def commute_oneline(advice, now) -> str   # compact one-liner for statusline use\n` +
    `tests/test_commute.py: with a fake config + fake now, morning picks home->work; leave_in_min = (train time - now) - buffer, never negative shown as 0/now; None when unconfigured. Use small injectable helpers so you don't need real time.`,
    { label: 'I:commute', phase: '功能模組', schema: { type: 'object', additionalProperties: false, properties: { file: { type: 'string' }, functions: { type: 'array', items: { type: 'string' } }, integration_hint: { type: 'string' }, notes: { type: 'string' } }, required: ['file'] } }
  ),
  // I-3 — local ICS agenda feed
  () => agent(
    `Implement a local iCalendar (.ics) agenda feed that maps calendar events to Departure objects (so the board can show "next meetings" like trains). ${COMMON}\n\n` +
    `File: ${PKG}/feeds.py\n` +
    `def departures_from_ics(path: str, now, limit: int = 6) -> list[Departure]\n` +
    `Parse VEVENT blocks with a SMALL hand-written parser (NO external deps): read DTSTART (handle 'YYYYMMDDTHHMMSS', with/without Z, and DATE-only) and SUMMARY; keep only events starting today and >= now; sort; take limit. Map each to Departure(time='HH:MM' of start, kind_jp='予定', dest_jp=SUMMARY (truncate long), track='', direction='agenda'). Handle missing file / malformed lines gracefully (return []).\n` +
    `tests/test_feeds.py: write a tiny .ics to tmp_path with 3 events (one past, two future) and assert only future ones returned, sorted, time formatted HH:MM, summary mapped to dest_jp.`,
    { label: 'I:feeds', phase: '功能模組', schema: { type: 'object', additionalProperties: false, properties: { file: { type: 'string' }, functions: { type: 'array', items: { type: 'string' } }, integration_hint: { type: 'string' }, notes: { type: 'string' } }, required: ['file'] } }
  ),
])
const hints = modules.filter(Boolean).map(m => `- ${m.file}: ${m.integration_hint || ''}`).join('\n')
log(`modules: ${modules.filter(Boolean).map(m => m.file).join(', ')}`)

phase('整合除錯')
const integration = await agent(
  `Integrate the new features into the CLI and DEBUG end-to-end. ${ENGINE}\n\n` +
  `New modules now exist (do NOT rewrite them, just wire them):\n${hints}\n\n` +
  `Config contract:\n${CONFIG_CONTRACT}\n\n` +
  `Tasks:\n` +
  `1. Edit ${PKG}/cli.py:\n` +
  `   - Load config via config.load_config() and use it for DEFAULTS of --line/--station/--columns/--width/--flap-steps/--flap-delay (CLI args still override).\n` +
  `   - Add subcommand-style flags (keep backward compatibility with existing flags):\n` +
  `       --tui                     -> jrboard.tui.run_tui(line, station, config)\n` +
  `       --pomodoro MIN            -> run a journey: build via journey.make_journey using --line and two stations (use --from/--to if given, else sensible defaults / endpoints), then loop rendering journey.render_journey each second with the flap intro, until arrival; respect --once.\n` +
  `       --commute                 -> render commute.commute_advice/render_commute (board) or, in --mode statusline, print commute.commute_oneline once.\n` +
  `       --feed-ics PATH           -> in board/statusline modes, use feeds.departures_from_ics(PATH, now, limit) INSTEAD of get_departures (source label 'AGENDA'); the rest of rendering unchanged.\n` +
  `   - Keep these additive and well-documented in --help.\n` +
  `2. Verify by RUNNING (paste evidence): \n` +
  `   - python3 ${PROJECT}/main.py --help\n` +
  `   - python3 ${PROJECT}/main.py --pomodoro 1 --line yamanote --once   (journey renders, shows あと/arrival)\n` +
  `   - printf 'BEGIN:VCALENDAR...' to a temp .ics then python3 ${PROJECT}/main.py --feed-ics /tmp/agenda.ics --mode statusline --columns 50\n` +
  `   - python3 ${PROJECT}/main.py --commute --mode statusline   (with a temp config setting home/work; show it works and that without config it gives a helpful message)\n` +
  `   - jrboard --list works after \`pip install -e .\` (try the entry point; if pip not desired, at least validate pyproject with python -m build --sdist or \`python -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"\`).\n` +
  `   - --tui: cannot drive curses headless; instead import jrboard.tui and call its PURE helpers to prove they work, and confirm \`python3 -c "import jrboard.tui"\` imports cleanly.\n` +
  `3. Run the FULL suite: python3 -m pytest ${PROJECT}/tests -q  (must stay green, including the pre-existing 50 tests).\n` +
  `4. Run a sweep: render a board --once --no-flap for several lines to confirm no regressions.\n` +
  `5. Update README.md / README.en.md / README.ja.md with a short new section documenting --tui, --pomodoro, --commute, --feed-ics, the config file, and \`pip install\` / entry point. Keep the three in sync.\n` +
  `Fix every traceback. Return a structured report with commands run + short output excerpts and the final test count.`,
  { label: 'integrate', phase: '整合除錯', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      cli_flags_added: { type: 'array', items: { type: 'string' } },
      commands_run: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, ok: { type: 'boolean' }, output_excerpt: { type: 'string' } }, required: ['cmd', 'ok'] } },
      bugs_fixed: { type: 'array', items: { type: 'string' } },
      total_tests: { type: 'number' },
      tests_passing: { type: 'boolean' },
      readme_updated: { type: 'boolean' },
      summary: { type: 'string' },
    },
    required: ['commands_run', 'tests_passing', 'summary'],
  } }
)

return {
  foundation: { files: foundation?.files, tests_passing: foundation?.tests_passing },
  modules: modules.filter(Boolean).map(m => m.file),
  integration,
}
