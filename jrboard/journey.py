"""Pomodoro-as-a-train-journey mode (pure logic + renderer).

A focus timer reframed as a train ride: the session is a :class:`Journey`
from an *origin* to a *destination*, and elapsed focus time is the train's
progress along the line. Everything here is pure -- no sleeping, no printing.
The renderer returns ``list[str]`` whose every row is exactly ``width`` visual
columns wide (CJK- and ANSI-aware via :mod:`jrboard.width`), matching the
framed board style of :mod:`jrboard.render`.

Public API:
    make_journey(line, origin, dest, start_epoch, duration_min) -> Journey
    progress(journey, now_epoch) -> float          # clamped 0..1
    remaining_sec(journey, now_epoch) -> int        # clamped >= 0
    render_journey(journey, now_epoch, width=60) -> list[str]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import width as _w
from .model import Line, Station

__all__ = [
    "Journey",
    "make_journey",
    "progress",
    "remaining_sec",
    "render_journey",
]

# --- ANSI palette (line colour injected per render) -------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Default labels when no real station pair is supplied.
_DEFAULT_ORIGIN_JP = "いま"
_DEFAULT_DEST_JP = "集中"

_SEC_PER_MIN = 60
_MIN_WIDTH = 24
_HEADER_JP = "集中タイマー"

# Track glyphs for the ASCII journey line.
_TRACK = "─"
_ORIGIN_DOT = "●"
_DEST_DOT = "◎"
_TRAIN = "▶"


@dataclass(frozen=True)
class Journey:
    """An immutable focus session modelled as a train ride.

    Attributes:
        line: The :class:`~jrboard.model.Line` the journey runs on (its colour
            palette is used for rendering).
        origin: Departure :class:`~jrboard.model.Station` (the "now" end).
        dest: Arrival :class:`~jrboard.model.Station` (the "focus" goal).
        start_epoch: Unix epoch seconds when focus began.
        duration_sec: Total session length in seconds (>= 0).
    """

    line: Line
    origin: Station
    dest: Station
    start_epoch: float
    duration_sec: int


def _label_station(name_jp: str, number: str = "", name_en: str = "") -> Station:
    """Build a lightweight placeholder :class:`Station` for label-only ends."""
    return Station(
        id=name_jp,
        number=number,
        name_jp=name_jp,
        kana="",
        name_en=name_en,
        odpt_station="",
    )


def _pick_station_pair(
    line: Line, duration_min: int
) -> tuple[Station, Station]:
    """Pick two real stations spaced ~proportional to ``duration_min``.

    Origin is the first station; the destination is chosen so that a longer
    focus session maps to a station further down the line (roughly one stop
    every few minutes, capped at the line's length). Falls back to label-only
    endpoints when the line has fewer than two usable stations.
    """
    stations = tuple(getattr(line, "stations", ()) or ())
    if len(stations) < 2:
        return (
            _label_station(_DEFAULT_ORIGIN_JP),
            _label_station(_DEFAULT_DEST_JP),
        )

    origin = stations[0]
    # ~1 stop per 5 focus minutes, at least one stop, capped at the last index.
    span = max(1, duration_min // 5)
    dest_index = min(span, len(stations) - 1)
    return origin, stations[dest_index]


def make_journey(
    line: Line,
    origin: Optional[Station],
    dest: Optional[Station],
    start_epoch: float,
    duration_min: int,
) -> Journey:
    """Create a :class:`Journey`.

    When both ``origin`` and ``dest`` are provided they are used as-is.
    Otherwise a station pair is derived from ``line`` spaced proportionally to
    ``duration_min`` (or label-only ``いま`` -> ``集中`` ends when the line has
    no usable station pair). ``duration_min`` is clamped to ``>= 0``.
    """
    duration_min = max(0, int(duration_min))
    if origin is not None and dest is not None:
        chosen_origin, chosen_dest = origin, dest
    else:
        chosen_origin, chosen_dest = _pick_station_pair(line, duration_min)

    return Journey(
        line=line,
        origin=chosen_origin,
        dest=chosen_dest,
        start_epoch=float(start_epoch),
        duration_sec=duration_min * _SEC_PER_MIN,
    )


def progress(journey: Journey, now_epoch: float) -> float:
    """Return fractional progress in ``[0.0, 1.0]`` (clamped).

    ``0.0`` at or before ``start_epoch``; ``1.0`` at or after arrival. A
    zero-length journey is treated as instantly complete.
    """
    if journey.duration_sec <= 0:
        return 1.0
    elapsed = float(now_epoch) - journey.start_epoch
    if elapsed <= 0.0:
        return 0.0
    fraction = elapsed / journey.duration_sec
    if fraction >= 1.0:
        return 1.0
    return fraction


def remaining_sec(journey: Journey, now_epoch: float) -> int:
    """Return whole seconds left until arrival, clamped to ``>= 0``."""
    if journey.duration_sec <= 0:
        return 0
    elapsed = float(now_epoch) - journey.start_epoch
    remaining = journey.duration_sec - elapsed
    if remaining <= 0.0:
        return 0
    return int(remaining + 0.5)  # round to nearest whole second


def _clamp_width(width: int) -> int:
    return _MIN_WIDTH if width < _MIN_WIDTH else width


def _frame_top(internal_w: int) -> str:
    return "+" + ("-" * internal_w) + "+"


def _frame_div(internal_w: int) -> str:
    return "|" + ("-" * internal_w) + "|"


def _truncate(text: str, max_w: int) -> str:
    """Truncate ``text`` to at most ``max_w`` visual columns (ANSI-aware).

    ANSI escape sequences are passed through and never counted; a trailing
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
    """Wrap ``content`` in the box frame at exact internal width."""
    return "|" + _w.safe_pad(_truncate(content, internal_w), internal_w) + "|"


def _centered_row(content: str, internal_w: int) -> str:
    fitted = _truncate(content, internal_w)
    return "|" + _w.safe_pad(fitted, internal_w, "center") + "|"


def _station_name(station: Station) -> str:
    """Best-effort JP name for a station/label end."""
    name = getattr(station, "name_jp", "") or getattr(station, "name_en", "")
    return name or getattr(station, "id", "") or "?"


def _fmt_remaining(seconds: int) -> str:
    """Big remaining label: ``あと N 分`` (minutes, rounded up while running)."""
    if seconds <= 0:
        return "とうちゃく"
    minutes = (seconds + _SEC_PER_MIN - 1) // _SEC_PER_MIN
    return f"あと {minutes} 分"


def _fmt_clock(epoch: float) -> str:
    """Format an epoch second into a local ``HH:MM`` arrival clock."""
    import time as _time

    try:
        lt = _time.localtime(epoch)
        return f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    except (OverflowError, OSError, ValueError):
        return "--:--"


def _track_line(frac: float, line: Line, internal_w: int) -> str:
    """Build the origin -> train -> dest ASCII track for the given fraction.

    Returns a coloured string measuring exactly ``internal_w`` visual columns.
    The train glyph sits at ``frac`` between the origin and destination dots.
    """
    fg = getattr(line, "ansi_fg", "") or ""
    # Reserve the two endpoint dots; the rest is the rail the train travels.
    rail_w = max(internal_w - 2, 1)
    # Train position along the rail (0 .. rail_w - 1).
    pos = int(round(frac * (rail_w - 1))) if rail_w > 1 else 0
    if pos < 0:
        pos = 0
    elif pos > rail_w - 1:
        pos = rail_w - 1

    before = _TRACK * pos
    after = _TRACK * (rail_w - 1 - pos)
    body = f"{_ORIGIN_DOT}{before}{_TRAIN}{after}{_DEST_DOT}"
    painted = f"{fg}{body}{RESET}" if fg else body
    # Guarantee exact width even if rounding/odd glyph widths drift.
    return _w.safe_pad(painted, internal_w, "center")


def _endpoints_row(journey: Journey, internal_w: int) -> str:
    """Origin name on the left, destination name on the right."""
    left = _station_name(journey.origin)
    right = _station_name(journey.dest)
    gap = internal_w - _w.get_visual_width(left) - _w.get_visual_width(right)
    if gap < 1:
        gap = 1
    return _row(left + " " * gap + right, internal_w)


def _progress_bar(frac: float, line: Line, internal_w: int) -> str:
    """A filled/empty progress bar measuring exactly ``internal_w`` columns.

    Layout: ``[<bar>] NNN%``. The trailing ``" NNN%"`` label and the two
    bracket cells are reserved first, so the bar fills the remaining columns
    and the whole row lands on exactly ``internal_w`` visual columns.
    """
    bg = getattr(line, "ansi_bg", "") or ""
    pct = int(round(frac * 100))
    pct_label = f" {pct:3d}%"  # 5 visual columns
    label_w = _w.get_visual_width(pct_label)

    # Reserve brackets (2) + the percentage label; the rest is the bar.
    bar_w = max(internal_w - 2 - label_w, 1)
    filled = int(round(frac * bar_w))
    if filled < 0:
        filled = 0
    elif filled > bar_w:
        filled = bar_w
    empty = bar_w - filled

    fill_seg = "█" * filled
    empty_seg = "░" * empty
    if bg:
        bar = f"{bg}{fill_seg}{RESET}{DIM}{empty_seg}{RESET}"
    else:
        bar = f"{fill_seg}{empty_seg}"
    content = f"[{bar}]{pct_label}"
    return _row(content, internal_w)


def render_journey(
    journey: Journey, now_epoch: float, width: int = 60
) -> list[str]:
    """Render the focus-journey board as a list of ANSI text lines.

    Layout (top to bottom):
        1. header ``集中タイマー`` + the line name
        2. the ASCII journey line (origin ● ── ▶ ── ◎ dest)
        3. origin / destination station names
        4. big remaining ``あと N 分`` (or ``とうちゃく`` on arrival)
        5. arrival clock (``HH:MM 着``)
        6. progress bar with percentage

    Every returned row is exactly ``width`` visual columns wide. Pure: no
    sleeping, no printing.
    """
    iw = _clamp_width(width) - 2
    line = journey.line
    fg = getattr(line, "ansi_fg", "") or ""
    name_jp = getattr(line, "name_jp", "") or ""
    name_en = getattr(line, "name_en", "") or ""

    frac = progress(journey, now_epoch)
    secs = remaining_sec(journey, now_epoch)
    arrival_epoch = journey.start_epoch + journey.duration_sec

    rows: list[str] = [_frame_top(iw)]

    # Row 1: header + line identity.
    head = f"  {BOLD}{_HEADER_JP}{RESET}  {DIM}{name_jp} {name_en}{RESET}"
    rows.append(_row(head, iw))
    rows.append(_frame_div(iw))

    # Row 2: the journey track with the moving train.
    rows.append(_row(_track_line(frac, line, iw), iw))

    # Row 3: endpoint station names.
    rows.append(_endpoints_row(journey, iw))
    rows.append(_frame_div(iw))

    # Row 4: big remaining label, centred and coloured.
    big = _fmt_remaining(secs)
    big_painted = f"{fg}{BOLD}{big}{RESET}" if fg else f"{BOLD}{big}{RESET}"
    rows.append(_centered_row(big_painted, iw))

    # Row 5: arrival clock.
    clock = f"{DIM}到着 {_fmt_clock(arrival_epoch)} 着{RESET}"
    rows.append(_centered_row(clock, iw))
    rows.append(_frame_div(iw))

    # Row 6: progress bar.
    rows.append(_progress_bar(frac, line, iw))

    rows.append(_frame_top(iw))
    return rows
