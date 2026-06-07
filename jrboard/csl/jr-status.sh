# Theme: jr-status — composed multi-row statusline (component-framework demo).
#
# REQUIRES the csl COMPONENT COMPOSER (lib/components.sh + a render() that
# dispatches on CSL_ROWS). Unlike jr-board/jr-timetable (which are self-contained
# and override render()), this theme declares CSL_ROWS and lets the engine
# assemble decoupled components — so it only composes on a csl build that has the
# component engine; on stock csl it falls back to the classic line.
#
#   Row 1: session/token components — model + context bar + 5h/7d gauges
#   Row 2: the JR / Tokyo Metro split-flap board (per-session line)
#
# Rearrange freely — each CSL_ROWS element is one OUTPUT LINE; within a line,
# space-separated component names render left-to-right. Available components:
#   user dir git model ctx tokens style clock jrboard jrtable
# Examples:
#   CSL_ROWS=( "jrboard" "model ctx tokens git" )            # board on top
#   CSL_ROWS=( "user dir git" "model ctx tokens" "jrboard" ) # three rows
#   CSL_ROWS=( "model ctx tokens" "jrtable" )                # multi-line table board
THEME_DESC="Composed multi-row: session/token gauges + JR board (component framework)"

CSL_ROWS=( "model ctx tokens" "jrboard" )
CSL_SEP=" · "                       # within-row separator
# Narrower than the board content so the marquee actually scrolls (a wider
# budget makes the board fit => nothing to scroll). Try 48–60.
CSL_COLUMNS="${CSL_COLUMNS:-50}"    # width budget passed to board components

# JR board component opt-ins (see lib/components.sh):
JR_BY_SESSION="${JR_BY_SESSION:-1}" # different Claude sessions => different lines
# JR_CITY="Tokyo"                    # scope the auto-picked line to a city
# JR_LINE=oedo ; JR_STATION=tochomae # or pin a specific line/station
