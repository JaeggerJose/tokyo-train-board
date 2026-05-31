# Theme: jr-board — JR / Tokyo Metro split-flap departure marquee.
#
# Overrides render() to show the next departures from a station as a single
# horizontally-scrolling line. The station name stays pinned on the left while
# the departures scroll past like an old station/airport flap board. Scrolling
# is driven by settings.json `refreshInterval` (offset advances ~1 column/sec).
#
# Customize: edit JR_LINE / JR_STATION / JR_COLUMNS below.
#   JR_LINE     any `--line` key (yamanote, ginza, oedo, chuo, sobu, ...)
#   JR_STATION  station name_en / id / number on that line
#   JR_COLUMNS  marquee width; narrower => more scrolling (try 56–90)
#   JR_SCROLL_ALL=1  scroll the whole line incl. station name (default: pinned)
THEME_DESC="JR / Tokyo Metro split-flap departure marquee"

JR_HOME="${JR_HOME:-/Users/minghsuan/Downloads/JR-timetable}"
JR_LINE="${JR_LINE:-yamanote}"
JR_STATION="${JR_STATION:-shinjuku}"
JR_COLUMNS="${JR_COLUMNS:-72}"
JR_SCROLL_ALL="${JR_SCROLL_ALL:-0}"

render() {
  # The statusline JSON ($1) is unused: this board shows transit data, not
  # session data. Kept in the signature for contract compatibility.
  local _input="$1"
  local scroll_flag=""
  [ "$JR_SCROLL_ALL" = "1" ] && scroll_flag="--scroll-all"

  local line
  line=$(python3 "$JR_HOME/main.py" \
           --mode statusline \
           --line "$JR_LINE" --station "$JR_STATION" \
           --columns "$JR_COLUMNS" $scroll_flag 2>/dev/null)

  # Never let a failed render blank the status line: fall back to a static hint.
  if [ -z "$line" ]; then
    line="[JR] ${JR_LINE}/${JR_STATION} ▸ (board unavailable — check ${JR_HOME})"
  fi
  printf '%s' "$line"
}
