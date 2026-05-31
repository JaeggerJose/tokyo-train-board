"""ANSI split-flap style board renderer for JR / Toei lines.

Pure rendering layer: every public function returns ``list[str]`` (lines that
may embed ANSI escape sequences) and never writes to stdout. Visual style
mirrors the original ``yamanote_board.py`` (box-drawing frame, green
navigation bar) but is generalized over :class:`model.Line`,
:class:`model.Station`, neighbour lookup and the line's own colour palette.

Width handling is delegated to :mod:`jrboard.width` so CJK glyphs and ANSI
sequences are measured correctly regardless of the configured board width.
"""

from __future__ import annotations

from typing import Sequence

from . import width as _w
from .model import Line, Station, neighbors
from .sources import Departure

# --- Shared ANSI palette (line colour is injected per render) ---------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ORANGE = "\033[38;5;208m"
GREEN_BG = "\033[48;5;28m\033[38;5;231m"  # white-on-green nav bar fallback
GREEN_FG = "\033[38;5;34m"

# Minimum internal width we are willing to render at; smaller frames look
# broken because the navigation bar and timetable columns collapse.
_MIN_WIDTH = 24


def _clamp_width(width: int) -> int:
    """Return a sane internal frame width (>= ``_MIN_WIDTH``)."""
    if width < _MIN_WIDTH:
        return _MIN_WIDTH
    return width


def _frame_top(internal_w: int) -> str:
    return "+" + ("-" * internal_w) + "+"


def _frame_div(internal_w: int) -> str:
    return "|" + ("-" * internal_w) + "|"


def _truncate(text: str, max_w: int) -> str:
    """Truncate ``text`` to at most ``max_w`` visual columns.

    ANSI sequences are preserved/passed through and never counted; a trailing
    reset is appended if any escape was opened. Wide (CJK) glyphs count as two
    columns so multi-byte characters are never split mid-glyph.
    """
    if _w.get_visual_width(text) <= max_w:
        return text
    out: list[str] = []
    used = 0
    saw_ansi = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\033":
            j = text.find("m", i)
            if j == -1:
                break
            out.append(text[i:j + 1])
            saw_ansi = True
            i = j + 1
            continue
        cw = 2 if _w.get_visual_width(ch) == 2 else 1
        if used + cw > max_w:
            break
        out.append(ch)
        used += cw
        i += 1
    result = "".join(out)
    if saw_ansi and not result.endswith(RESET):
        result += RESET
    return result


def _row(content: str, internal_w: int) -> str:
    """Wrap ``content`` in the box frame, fitted to exact internal width."""
    fitted = _truncate(content, internal_w)
    return "|" + _w.safe_pad(fitted, internal_w) + "|"


def _badge(text: str, line: Line) -> str:
    """Coloured station-number badge using the line's background colour."""
    return f"{line.ansi_bg} {text} {RESET}"


def _spaced_name(name_jp: str) -> str:
    """Space out short JP names the way station signage does (新 宿)."""
    if 1 <= len(name_jp) <= 4:
        return "  ".join(name_jp)
    return name_jp


def render_station_sign(line: Line, station: Station, width: int = 60) -> list[str]:
    """Render the station nameplate as a list of ANSI text lines.

    Layout (top to bottom):
      1. line symbol badge (left) + line name (right)
      2. station-number badge (left) + big spaced JP name (centre)
      3. kana reading + English name (centre)
      4. green navigation bar: prev / current / next (JP)
      5. English navigation row: prev / current / next
    """
    iw = _clamp_width(width) - 2
    prev_st, curr_st, next_st = neighbors(line, station)

    lines: list[str] = [_frame_top(iw)]

    # Row 1: line symbol + line name.
    sym = _badge(line.symbol, line)
    head = f"  {sym}  {DIM}{line.name_jp}  {line.name_en}{RESET}"
    lines.append(_row(head, iw))

    # Row 2: station number badge + big centred JP name.
    num_badge = _badge(f"{line.symbol} {station.number}", line)
    left = f"  {num_badge}"
    left_w = _w.get_visual_width(left)
    name_field = max(iw - left_w - 2, 4)
    big_name = _w.safe_pad(f"{BOLD}{_spaced_name(station.name_jp)}{RESET}",
                           name_field, "center")
    lines.append(_row(left + big_name, iw))

    # Row 3: kana + English, centred.
    sub = f"{station.kana}   {station.name_en}"
    lines.append(_row(_w.safe_pad(sub, iw, "center"), iw))

    # Row 4: green navigation bar (JP).
    nav_jp = _truncate(
        _nav_content(
            _prev_label(prev_st, "name_jp", "◀ "),
            "■",
            _next_label(next_st, "name_jp", " ▶"),
            iw,
        ),
        iw,
    )
    lines.append("|" + GREEN_BG + _w.safe_pad(nav_jp, iw) + RESET + "|")

    # Row 5: English navigation row.
    lines.append(_row(
        _nav_content(
            _prev_label(prev_st, "name_en", "< "),
            station.name_en,
            _next_label(next_st, "name_en", " >"),
            iw,
        ),
        iw,
    ))

    lines.append(_frame_top(iw))
    return lines


def _prev_label(st: Station | None, attr: str, mark: str) -> str:
    if st is None:
        return ""
    return f"{mark}{getattr(st, attr)}"


def _next_label(st: Station | None, attr: str, mark: str) -> str:
    if st is None:
        return ""
    return f"{getattr(st, attr)}{mark}"


def _nav_content(prev: str, curr: str, nxt: str, internal_w: int) -> str:
    """Three-column nav row: prev (left) / curr (centre) / next (right)."""
    inner = internal_w - 4  # account for the 2-space margins
    if inner < 6:
        inner = internal_w
        margin = ""
    else:
        margin = "  "
    third = max(inner // 3, 1)
    curr_w = inner - third * 2
    return (
        margin
        + _w.safe_pad(_truncate(prev, third), third, "left")
        + _w.safe_pad(_truncate(curr, curr_w), curr_w, "center")
        + _w.safe_pad(_truncate(nxt, third), third, "right")
        + margin
    )


def render_timetable(
    line: Line,
    departures: Sequence[Departure],
    width: int = 60,
    source_label: str = "STATIC",
) -> list[str]:
    """Render the departures timetable as a list of ANSI text lines.

    Columns: time (時刻) / kind (種別) / destination (行先・方面) / track (番線).
    Column widths flex with the configured board width; the destination column
    absorbs the remaining space. A discreet source label (ODPT/STATIC) is shown
    in the footer.
    """
    iw = _clamp_width(width) - 2

    # Fixed-ish columns; destination flexes. Separators: " | " (x3) + edges.
    time_w = 6
    kind_w = 10
    track_w = 4
    sep = 3  # width of " | "
    # leading + trailing single space + 3 separators.
    fixed = 1 + time_w + 1 + sep + kind_w + sep + track_w + 1 + sep
    dest_w = max(iw - fixed, 8)

    lines: list[str] = []

    header = (
        f" {_w.safe_pad('時刻', time_w)} | "
        f"{_w.safe_pad('種別', kind_w)} | "
        f"{_w.safe_pad('行先 (方面)', dest_w)} | "
        f"{_w.safe_pad('番線', track_w)} "
    )
    lines.append(_row(header, iw))
    lines.append(_frame_div(iw))

    if not departures:
        empty = _truncate(
            f"{DIM}本日の運行は終了しました / No further departures{RESET}",
            iw,
        )
        lines.append(_row(_w.safe_pad(empty, iw, "center"), iw))
    else:
        for dep in departures:
            time_cell = f"{ORANGE}{dep.time}{RESET}"
            kind_cell = f"{line.ansi_fg}{dep.kind_jp}{RESET}"
            row = (
                f" {_w.safe_pad(time_cell, time_w)} | "
                f"{_w.safe_pad(kind_cell, kind_w)} | "
                f"{_w.safe_pad(dep.dest_jp, dest_w)} | "
                f"{_w.safe_pad(dep.track, track_w)} "
            )
            lines.append(_row(row, iw))

    lines.append(_frame_div(iw))

    footer_left = f"{DIM}{line.name_en}{RESET}"
    footer_right = f"{DIM}src: {source_label}{RESET}"
    pad = iw - _w.get_visual_width(footer_left) - _w.get_visual_width(footer_right) - 2
    if pad < 1:
        pad = 1
    footer = f" {footer_left}{' ' * pad}{footer_right} "
    lines.append(_row(footer, iw))
    lines.append(_frame_top(iw))
    return lines


def render_board(
    line: Line,
    station: Station,
    departures: Sequence[Departure],
    width: int = 60,
    source_label: str = "STATIC",
) -> list[str]:
    """Combine the station sign and the timetable into one board."""
    sign = render_station_sign(line, station, width)
    table = render_timetable(line, departures, width, source_label)
    return sign + table
