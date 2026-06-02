export const meta = {
  name: 'jr-statusline-tokens',
  description: 'Statusline: read Claude statusLine JSON (session_id + rate limits), add per-session/rotate/city line selection, token gauges (5h session + 7d weekly), and two variants (marquee + minitable) with csl themes',
  phases: [
    { title: 'Python', detail: 'claude-stdin parsing, token gauges, by-session/rotate/city, minitable mode + tests' },
    { title: 'csl 主題', detail: 'jr-board (marquee) + jr-timetable (minitable) themes piping stdin JSON' },
    { title: '整合驗證', detail: 'simulate Claude JSON end-to-end, tests, READMEs' },
  ],
}

const PROJECT = '/Users/minghsuan/Downloads/JR-timetable'
const PKG = `${PROJECT}/jrboard`

const ENGINE = `
EXISTING package at ${PKG} (Python 3.11+, PEP8, type hints, frozen dataclasses, errors handled, no mutation). Reuse — do NOT reimplement:
- jrboard/model.py:  Line(key,name_jp,name_en,symbol,operator,odpt_railway,loop,ansi_fg,ansi_bg,hex,stations,first_train,last_train,headway_min,directions,city) ; Station(id,number,name_jp,kana,name_en,odpt_station) ; available_lines()->list[str] ; load_line(key)->Line ; find_station(line,key)->Station
- jrboard/sources.py: Departure(time,kind_jp,dest_jp,track,direction) ; get_departures(line,station,now,limit)->(list[Departure],label)
- jrboard/statusline.py: statusline_text(line,station,departures,now,columns=0,pin_label=True,color=True)->str  (single-line marquee; pins station label, scrolls departures; truecolor)
- jrboard/width.py: get_visual_width(text)->int ; safe_pad(text,target_w,align)->str
- jrboard/cli.py: main()->int ; existing flags incl --mode {board,statusline}, --line, --station, --city, --rotate, --columns, --color/--no-color, --scroll-all, --pin/--scroll-all
- jrboard/config.py: load_config()->Config
`

const CLAUDE_JSON = `
The Claude Code statusLine command receives a JSON object on STDIN. Relevant fields (all optional — be defensive):
  .session_id                              -> str (stable per session)
  .workspace.current_dir or .cwd           -> str (project dir)
  .model.display_name                      -> str
  .context_window.used_percentage          -> number (0-100)
  .rate_limits.five_hour.used_percentage   -> number (0-100)  == SESSION token limit
  .rate_limits.seven_day.used_percentage   -> number (0-100)  == WEEKLY token limit
Any field may be missing; never crash, just omit that piece.
`

phase('Python')
const py = await agent(
  `Implement statusline enhancements for the jrboard package. ${ENGINE}\n\n${CLAUDE_JSON}\n\n` +
  `Create a new module ${PKG}/claude_input.py with PURE, tested helpers:\n` +
  `  @dataclass(frozen=True) class ClaudeStatus: session_id:str|None; cwd:str|None; model:str|None; ctx_pct:float|None; session_pct:float|None; weekly_pct:float|None\n` +
  `  def parse_claude_status(raw: str) -> ClaudeStatus   # tolerant JSON parse of the stdin blob; missing/garbage -> all-None, never raises\n` +
  `  def pick_by_session(keys: list[str], session_id: str) -> str   # deterministic: stable hash(session_id) % len(keys); same session -> same key\n` +
  `  def pick_by_rotation(keys: list[str], now_epoch: float, period_sec: int) -> str   # keys[(int(now_epoch)//period_sec) % len(keys)] ; advances every period_sec\n` +
  `  def scope_keys_by_city(keys: list[str], city: str|None) -> list[str]   # filter to lines whose Line.city matches (case-insensitive); empty match -> original list\n` +
  `  def token_gauge(session_pct: float|None, weekly_pct: float|None, ctx_pct: float|None=None, color: bool=True) -> str\n` +
  `      # compact segment like '5h 42% · 7d 18%' (+ optional 'ctx 30%'); colour by threshold (<70 green, 70-89 yellow, >=90 red) using ANSI 38;2 or 38;5; '' when all None.\n` +
  `      # 5h = session limit, 7d = weekly limit. Keep it short (statuslines are width-constrained).\n\n` +
  `Then extend ${PKG}/statusline.py with a MINITABLE renderer:\n` +
  `  def minitable_text(line, station, departures, now, columns:int=0, color:bool=True, token_seg:str='') -> str\n` +
  `      # returns a MULTI-LINE string (newline-joined): line 1 = '[SYM] <num> <station_jp>' + (token_seg if given), line colour;\n` +
  `      # next 2-3 lines = upcoming departures 'HH:MM  方面' (line-coloured times). No trailing newline. Pure.\n\n` +
  `Then wire ${PKG}/cli.py (statusline path) — ADD these without breaking existing flags:\n` +
  `  --claude-stdin   : read+parse the Claude JSON from sys.stdin (only if not a tty / data available); use it for line selection + tokens.\n` +
  `  --by-session     : pick the line via claude_input.pick_by_session(session_id, pool) — pool = city-scoped available_lines(); needs session_id from --claude-stdin (fallback to rotation/default if absent).\n` +
  `  --tokens         : append claude_input.token_gauge(session_pct, weekly_pct, ctx_pct) to the output.\n` +
  `  --mode minitable : render via statusline.minitable_text instead of statusline_text.\n` +
  `  Make --rotate work in statusline too (time-bucketed via pick_by_rotation, default period 30s, --rotate as minutes already exists for board; for statusline treat --rotate value as MINUTES too, period = rotate*60, default 0.5 min if --rotate given with no value). --city scopes the pool.\n` +
  `  Selection precedence (statusline/minitable): explicit --line/--station > --by-session > --rotate > config/default. Always honour --city scoping for by-session/rotate.\n` +
  `  When a line is auto-picked (by-session/rotate), pick a sensible station: the line's flagship/default or its middle station; keep it stable for by-session.\n\n` +
  `Add tests: ${PROJECT}/tests/test_claude_input.py (parse good/garbage/missing fields; pick_by_session deterministic + same-session-stable + distributes; pick_by_rotation advances with time; scope_keys_by_city; token_gauge formatting + thresholds + empty) and extend statusline tests for minitable (multi-line, line1 has station, width respected, token_seg appended).\n\n` +
  `Run python3 -m pytest ${PROJECT}/tests -q and ruff check; everything must pass. Return the exact new CLI usage strings and public functions.`,
  { label: 'py:statusline', phase: 'Python', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      files: { type: 'array', items: { type: 'string' } },
      cli_usage: { type: 'array', items: { type: 'string' } },
      functions: { type: 'array', items: { type: 'string' } },
      tests_passing: { type: 'boolean' },
      total_tests: { type: 'number' },
      notes: { type: 'string' },
    },
    required: ['files', 'cli_usage', 'tests_passing'],
  } }
)
log(`python: ${py?.total_tests} tests, files=${(py?.files||[]).length}`)
const CLI_USAGE = JSON.stringify(py?.cli_usage ?? [], null, 0)

phase('csl 主題')
const themes = await agent(
  `Create two csl statusline themes that drive the jrboard statusline, passing the Claude statusLine JSON through to it. ${CLAUDE_JSON}\n\n` +
  `Background: csl themes live at ~/.config/csl/themes/<name>.sh (+ <name>.json manifest). A theme is sourced by run.sh AFTER lib/render.sh, then \`render "$input"\` is called with the statusLine JSON as $1. Overriding render() in the theme replaces the default. The EXISTING ~/.config/csl/themes/jr-board.sh already overrides render() to call \`python3 "$JR_HOME/main.py" --mode statusline ...\` with JR_LINE/JR_STATION/JR_COLUMNS/JR_SCROLL_ALL vars. JR_HOME defaults to ${PROJECT}.\n\n` +
  `The jrboard CLI now supports (from phase 1): ${CLI_USAGE}\n` +
  `Key new flags: --claude-stdin (read JSON from stdin), --tokens, --by-session, --mode minitable, plus existing --city/--rotate/--columns/--line/--station/--no-color/--scroll-all.\n\n` +
  `Write/UPDATE these (use the Write tool), then copy each into ${PROJECT}/integrations/csl/ too:\n` +
  `1. ~/.config/csl/themes/jr-board.sh — UPDATE the existing marquee theme: render() must pipe the statusLine JSON to jrboard so tokens + per-session work, e.g.:\n` +
  `     printf '%s' "$_input" | python3 "$JR_HOME/main.py" --mode statusline --claude-stdin --tokens \\\n` +
  `       \${JR_CITY:+--city "$JR_CITY"} \${JR_BY_SESSION:+--by-session} \${JR_ROTATE:+--rotate "$JR_ROTATE"} \\\n` +
  `       \${JR_LINE:+--line "$JR_LINE"} \${JR_STATION:+--station "$JR_STATION"} --columns "\${JR_COLUMNS:-72}" $scroll_flag\n` +
  `   Keep config vars at top with comments: JR_CITY, JR_BY_SESSION(=1), JR_ROTATE(minutes), JR_LINE, JR_STATION, JR_COLUMNS, JR_SCROLL_ALL. Default behaviour: JR_BY_SESSION=1 (so different sessions show different lines), JR_TOKENS on. Keep a static fallback line if jrboard fails.\n` +
  `   + jr-board.json manifest (description mentions tokens + per-session).\n` +
  `2. ~/.config/csl/themes/jr-timetable.sh — NEW theme: same idea but \`--mode minitable\` (multi-line: header+tokens then 2-3 departures). Same JR_* vars. + jr-timetable.json manifest.\n\n` +
  `IMPORTANT: pass the JSON via stdin (printf '%s' "$_input" | ...); do NOT interpolate untrusted JSON into the command line. Quote variables. Never let a failed render blank the status line (fallback text).\n` +
  `Verify locally: pipe a sample JSON and run each theme's render through bash, show the output. Return the theme file paths + the exact sample command you used.`,
  { label: 'csl:themes', phase: 'csl 主題', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      files: { type: 'array', items: { type: 'string' } },
      sample_cmd: { type: 'string' },
      sample_output: { type: 'string' },
      notes: { type: 'string' },
    },
    required: ['files'],
  } }
)
log(`themes: ${(themes?.files||[]).join(', ')}`)

phase('整合驗證')
const verify = await agent(
  `Verify the statusline token + per-session + variants feature end-to-end and document it. ${ENGINE}\n\n${CLAUDE_JSON}\n\n` +
  `Phase-1 CLI usage: ${CLI_USAGE}\n` +
  `Phase-2 themes: ${JSON.stringify(themes?.files ?? [])}\n\n` +
  `Do and paste evidence:\n` +
  `1. Build a realistic sample Claude statusLine JSON (with session_id, rate_limits.five_hour.used_percentage=42, rate_limits.seven_day.used_percentage=18, context_window.used_percentage=30, workspace.current_dir). Save to /tmp/cc.json.\n` +
  `2. MARQUEE: cat /tmp/cc.json | python3 ${PROJECT}/main.py --mode statusline --claude-stdin --tokens --by-session --city Tokyo --columns 72   — confirm ONE line with a train marquee + '5h 42% · 7d 18%' tokens; confirm a DIFFERENT session_id yields a DIFFERENT line (run twice with two ids), and the SAME id is stable.\n` +
  `3. MINITABLE: cat /tmp/cc.json | python3 ${PROJECT}/main.py --mode minitable --claude-stdin --tokens --rotate --city Kyoto --columns 60   — confirm MULTI-LINE (header+tokens then departures).\n` +
  `4. ROTATE over time: show that --rotate selects different lines at two different fake times (or two runs spaced in time), scoped to --city.\n` +
  `5. csl path: printf the sample JSON through \`bash ~/.claude/statusline/run.sh jr-board\` and \`... jr-timetable\` (CSL_HOME if needed). Strip ANSI in the pasted excerpt. Confirm both render and include tokens.\n` +
  `6. Full suite: python3 -m pytest ${PROJECT}/tests -q (must pass) + ruff check ${PKG}.\n` +
  `7. Update README.md / README.en.md / README.ja.md: a short subsection under the statusline docs covering --tokens (session 5h + weekly 7d), --by-session (different sessions -> different lines), statusline --rotate/--city, the new minitable mode, and the two csl themes (jr-board vs jr-timetable). Document HOW to vary statuslines per session: (a) JR_BY_SESSION=1 auto-varies by session_id; (b) per-project .claude/settings.json statusLine override. Keep the 3 READMEs in sync.\n` +
  `Fix any traceback or failing test. Report commands + short output excerpts + final test count.`,
  { label: 'verify+docs', phase: '整合驗證', schema: {
    type: 'object', additionalProperties: false,
    properties: {
      commands_run: { type: 'array', items: { type: 'object', properties: { cmd: { type: 'string' }, ok: { type: 'boolean' }, output_excerpt: { type: 'string' } }, required: ['cmd', 'ok'] } },
      different_sessions_differ: { type: 'boolean' },
      tokens_shown: { type: 'boolean' },
      minitable_multiline: { type: 'boolean' },
      tests_passing: { type: 'boolean' },
      total_tests: { type: 'number' },
      readmes_updated: { type: 'boolean' },
      bugs_fixed: { type: 'array', items: { type: 'string' } },
      summary: { type: 'string' },
    },
    required: ['commands_run', 'tests_passing', 'summary'],
  } }
)

return { python: py, themes, verify }
