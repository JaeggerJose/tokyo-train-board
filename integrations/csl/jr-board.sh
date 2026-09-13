# Theme: jr-board — JR / Tokyo Metro split-flap departure marquee (Claude-aware).
#
# Overrides render() to show the next departures from a station as a single
# horizontally-scrolling line, with Claude token/context gauges appended on the
# right (5h session / 7d weekly / context). The Claude statusLine JSON ($1) is
# piped to jrboard via STDIN (never interpolated into the command line) so it
# can read session_id + rate limits + context fill. Scrolling advances via
# settings.json `refreshInterval` (~1 column/sec).
#
# Default behaviour: per-project (JR_BY_PROJECT=1) so each Claude project keeps
# its OWN fixed line, with token gauges on (JR_TOKENS=1).
#
# Customize the vars below:
#   JR_CITY       scope line selection to a city (Tokyo/Osaka/Kyoto/Sapporo/
#                 Otaru). EMPTY = all cities.
#   JR_BY_PROJECT =1 (default) deterministic line from the Claude project dir:
#                 every project gets its own line. Set 0/empty to disable.
#                 Only takes effect when JR_LINE is EMPTY.
#   JR_BY_SESSION =1 (opt-in) deterministic line from session_id instead.
#                 by-project wins over by-session.
#   JR_ROTATE     minutes; rotate through the (city-scoped) pool over time
#                 (e.g. 0.5 = 30s, 2 = 2min). Only when JR_LINE is empty.
#                 by-project / by-session win over rotate.
#   JR_LINE       pin a line key (yamanote, ginza, oedo, …). When set it
#                 overrides by-project / by-session / rotate.
#   JR_STATION    station name_en / id / number (used with JR_LINE).
#   JR_COLUMNS    marquee width; narrower => more scrolling (try 50–90).
#   JR_SCROLL_ALL =1 scroll the whole line incl. station name (default: pinned).
#   JR_PYTHON     python that has tokyo-train-board installed (default python3;
#                 use a venv/pipx path if you installed there).
#   JR_HOME       optional path to a repo checkout; when unset the pip-installed
#                 package (python -m jrboard) is used — no clone needed.
THEME_DESC="JR / Tokyo Metro split-flap marquee + Claude token gauges (per-project)"

JR_PYTHON="${JR_PYTHON:-python3}"   # python with tokyo-train-board installed
JR_HOME="${JR_HOME:-}"              # optional repo checkout; empty => use pip package

# --- config -----------------------------------------------------------------
JR_CITY="${JR_CITY:-}"              # e.g. Tokyo / Osaka / Kyoto. Empty = all.
JR_BY_PROJECT="${JR_BY_PROJECT:-1}" # 1 = fixed line per project (default)
JR_BY_SESSION="${JR_BY_SESSION:-0}" # 1 = line per session (by-project wins)
JR_ROTATE="${JR_ROTATE:-}"          # minutes per rotation; empty = off
JR_LINE="${JR_LINE:-}"              # pin a line (overrides by-project/session/rotate)
JR_STATION="${JR_STATION:-}"        # station on the pinned line
JR_COLUMNS="${JR_COLUMNS:-72}"      # marquee width
JR_SCROLL_ALL="${JR_SCROLL_ALL:-0}" # 1 = scroll station name too
JR_TOKENS="${JR_TOKENS:-1}"         # 1 = append 5h/7d/ctx gauges (default)
# ----------------------------------------------------------------------------

render() {
  # $1 is the Claude statusLine JSON. Piped to jrboard via STDIN so --tokens
  # can parse session_id / rate limits / context window.
  local _input="$1"

  local scroll_flag=""
  [ "$JR_SCROLL_ALL" = "1" ] && scroll_flag="--scroll-all"
  local tokens_flag=""
  [ "$JR_TOKENS" = "1" ] && tokens_flag="--tokens"
  local session_flag=""
  [ "$JR_BY_SESSION" = "1" ] && session_flag="--by-session"
  local project_flag=""
  [ "$JR_BY_PROJECT" = "1" ] && project_flag="--by-project"

  # Prefer the pip-installed package; fall back to a repo checkout if JR_HOME set.
  local runner
  if [ -n "$JR_HOME" ] && [ -f "$JR_HOME/main.py" ]; then
    runner=("$JR_PYTHON" "$JR_HOME/main.py")
  else
    runner=("$JR_PYTHON" -m jrboard)
  fi

  local line
  line=$(printf '%s' "$_input" | "${runner[@]}" \
           --mode statusline --claude-stdin $tokens_flag $project_flag $session_flag \
           ${JR_CITY:+--city "$JR_CITY"} \
           ${JR_ROTATE:+--rotate "$JR_ROTATE"} \
           ${JR_LINE:+--line "$JR_LINE"} \
           ${JR_STATION:+--station "$JR_STATION"} \
           --columns "$JR_COLUMNS" $scroll_flag 2>/dev/null)

  # Never let a failed render blank the status line: fall back to a static hint.
  if [ -z "$line" ]; then
    line="[JR] ${JR_LINE:-auto} ▸ (board unavailable — pip install tokyo-train-board)"
  fi
  printf '%s' "$line"
}
