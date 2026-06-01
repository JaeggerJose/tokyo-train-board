"""Interactive curses TUI for jrboard.

A two-pane terminal UI:

* **Left pane** -- a scrollable, fuzzy-filterable list of every available line
  (``available_lines()``), each shown as ``symbol  name_jp`` in the line's own
  colour.
* **Right pane** -- the live departure board (:func:`render.render_board`) for
  the currently selected line + station, in colour, with a split-flap intro
  animation whenever the target line/station changes.

Colour note: curses cannot use 24-bit truecolor, so the board's truecolor ANSI
is mapped to the nearest xterm-256 index (works on any ``COLORS>=256`` terminal
without needing ``can_change_color``). Slight colour drift vs the non-TUI board
is expected; the line identity (green/orange/red…) still reads clearly.

Design split:

* All decision logic (fuzzy filtering, station stepping with loop wrap,
  favourite toggling, selection clamping) plus the pure colour/ANSI helpers
  (:func:`rgb_to_xterm256`, :func:`parse_ansi_runs`) live as **pure functions**
  so they are unit-testable without a TTY.
* Everything that touches :mod:`curses`, the clock, or persistence is confined
  to :func:`run_tui` and its private driver, which never raises out of the loop.
"""

from __future__ import annotations

import curses
import locale
import re
import sys
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional, Sequence

from . import flap, render
from .config import Config, load_config, load_favorites, save_favorites
from .model import (
    Line,
    Station,
    available_lines,
    find_station,
    load_line,
    neighbors,
)
from .sources import get_departures

__all__ = [
    "run_tui",
    "fuzzy_filter",
    "clamp_index",
    "step_station_key",
    "toggle_favorite",
    "next_favorite_index",
    "FilterState",
    "rgb_to_xterm256",
    "parse_ansi_runs",
]

# Periodic re-render cadence (ms) when idle; faster cadence while animating.
_REFRESH_MS = 1000
_FLAP_MS = 45
_FLAP_STEPS = 12

# Minimum usable geometry; below this we show a friendly hint.
_MIN_COLS = 30
_MIN_ROWS = 8

# Left list pane sizing.
_LIST_MIN_W = 16
_LIST_MAX_W = 28
_BOARD_MIN_W = render._MIN_WIDTH


# --------------------------------------------------------------------------- #
# Pure helpers (no curses / no IO) -- unit-tested.                            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FilterState:
    """Result of applying a fuzzy filter to the line list."""

    keys: tuple[str, ...]
    selected: int


def _subsequence_match(needle: str, haystack: str) -> bool:
    """Return True if ``needle`` is a case-insensitive subsequence of ``haystack``."""
    needle = needle.lower()
    if not needle:
        return True
    haystack = haystack.lower()
    it = iter(haystack)
    return all(ch in it for ch in needle)


def fuzzy_filter(
    keys: Sequence[str],
    query: str,
    labels: Optional[dict[str, str]] = None,
) -> tuple[str, ...]:
    """Return the subset of ``keys`` matching ``query`` as a fuzzy subsequence."""
    q = query.strip()
    if not q:
        return tuple(keys)
    out: list[str] = []
    for key in keys:
        label = labels.get(key, "") if labels else ""
        if _subsequence_match(q, key) or (label and _subsequence_match(q, label)):
            out.append(key)
    return tuple(out)


def clamp_index(index: int, length: int) -> int:
    """Clamp ``index`` into ``[0, length - 1]``; ``-1`` when ``length == 0``."""
    if length <= 0:
        return -1
    if index < 0:
        return 0
    if index >= length:
        return length - 1
    return index


def step_station_key(line: Line, current: Station, delta: int) -> str:
    """Return the station key one step from ``current`` along ``line``."""
    if delta == 0:
        return current.id
    prev_st, _curr, next_st = neighbors(line, current)
    target = next_st if delta > 0 else prev_st
    if target is None:
        return current.id
    return target.id


def toggle_favorite(
    favorites: Sequence[tuple[str, str]],
    pair: tuple[str, str],
) -> list[tuple[str, str]]:
    """Return a new favourites list with ``pair`` toggled (never mutates input)."""
    favs = list(favorites)
    if pair in favs:
        return [fav for fav in favs if fav != pair]
    return favs + [pair]


def next_favorite_index(
    favorites: Sequence[tuple[str, str]],
    current_index: int,
) -> int:
    """Return the next index to cycle to in ``favorites`` (wrapping); -1 if empty."""
    count = len(favorites)
    if count == 0:
        return -1
    return (current_index + 1) % count


def line_labels(keys: Sequence[str]) -> dict[str, str]:
    """Build a ``{key: name_jp}`` label map, skipping lines that fail to load."""
    labels: dict[str, str] = {}
    for key in keys:
        try:
            labels[key] = load_line(key).name_jp
        except (ValueError, TypeError):
            continue
    return labels


def rgb_to_xterm256(r: int, g: int, b: int) -> int:
    """Map a 24-bit RGB colour to the nearest xterm-256 palette index.

    Uses the 6x6x6 colour cube (indices 16-231) for chromatic colours and the
    24-step grayscale ramp (232-255) for near-greys, picking whichever is
    closer. curses can address these indices directly on a 256-colour terminal,
    so this is how truecolor line colours survive into the TUI.
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    def cube_axis(v: int) -> int:
        # xterm cube levels are 0,95,135,175,215,255.
        if v < 48:
            return 0
        if v < 115:
            return 1
        return min(5, (v - 35) // 40)

    ri, gi, bi = cube_axis(r), cube_axis(g), cube_axis(b)
    levels = (0, 95, 135, 175, 215, 255)
    cube_idx = 16 + 36 * ri + 6 * gi + bi
    cube_dist = (
        (levels[ri] - r) ** 2 + (levels[gi] - g) ** 2 + (levels[bi] - b) ** 2
    )

    # Grayscale candidate.
    gray = round((r + g + b) / 3)
    if gray < 8:
        gidx, gval = 16, 0
    elif gray > 238:
        gidx, gval = 231, 255
    else:
        step = round((gray - 8) / 10)
        gidx = 232 + min(23, max(0, step))
        gval = 8 + 10 * min(23, max(0, step))
    gray_dist = (gval - r) ** 2 + (gval - g) ** 2 + (gval - b) ** 2

    return gidx if gray_dist < cube_dist else cube_idx


_SGR_RE = re.compile(r"\033\[([0-9;]*)m")


def parse_ansi_runs(
    text: str,
) -> list[tuple[str, Optional[int], Optional[int]]]:
    """Split ANSI-coloured ``text`` into ``(segment, fg256, bg256)`` runs.

    Tracks SGR colour state across the string: ``38;2;r;g;b`` / ``48;2;r;g;b``
    truecolor codes are mapped via :func:`rgb_to_xterm256`; ``38;5;n`` / ``48;5;n``
    indexed codes are kept as-is; ``0`` resets. Other attributes are ignored.
    ``fg``/``bg`` are ``None`` when default. This is what lets the curses board
    reproduce the badge / time / line colours segment by segment.
    """
    runs: list[tuple[str, Optional[int], Optional[int]]] = []
    fg: Optional[int] = None
    bg: Optional[int] = None
    pos = 0
    for m in _SGR_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], fg, bg))
        body = m.group(1)
        nums = [int(p) for p in body.split(";") if p.isdigit()] if body else [0]
        if not nums:
            nums = [0]
        i = 0
        while i < len(nums):
            n = nums[i]
            if n == 0:
                fg = bg = None
                i += 1
            elif n in (38, 48) and i + 1 < len(nums) and nums[i + 1] == 2 and i + 4 < len(nums):
                idx = rgb_to_xterm256(nums[i + 2], nums[i + 3], nums[i + 4])
                if n == 38:
                    fg = idx
                else:
                    bg = idx
                i += 5
            elif n in (38, 48) and i + 1 < len(nums) and nums[i + 1] == 5 and i + 2 < len(nums):
                if n == 38:
                    fg = nums[i + 2]
                else:
                    bg = nums[i + 2]
                i += 3
            elif n == 39:
                fg = None
                i += 1
            elif n == 49:
                bg = None
                i += 1
            else:
                i += 1  # bold/dim/etc. -- ignored for colour purposes
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], fg, bg))
    return runs


def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


# --------------------------------------------------------------------------- #
# Curses colour layer.                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class _Colors:
    """Lazy curses colour-pair allocator keyed by (fg256, bg256)."""

    enabled: bool
    _pairs: dict[tuple[int, int], int] = field(default_factory=dict)
    _next: int = 1

    def attr(self, fg: Optional[int], bg: Optional[int]) -> int:
        """Return a curses attr for the given 256 colours (0 if unavailable)."""
        if not self.enabled:
            return 0
        fg_i = -1 if fg is None else min(fg, curses.COLORS - 1)
        bg_i = -1 if bg is None else min(bg, curses.COLORS - 1)
        if fg_i == -1 and bg_i == -1:
            return 0
        cache_key = (fg_i, bg_i)
        pair = self._pairs.get(cache_key)
        if pair is None:
            if self._next >= min(curses.COLOR_PAIRS, 255):
                return 0
            try:
                curses.init_pair(self._next, fg_i, bg_i)
            except curses.error:
                return 0
            pair = self._next
            self._pairs[cache_key] = pair
            self._next += 1
        return curses.color_pair(pair)


def _init_colors(use_color: bool) -> _Colors:
    """Enable curses colour where the terminal supports it; degrade gracefully."""
    if not use_color or not curses.has_colors():
        return _Colors(enabled=False)
    try:
        curses.start_color()
        curses.use_default_colors()
    except curses.error:
        return _Colors(enabled=False)
    return _Colors(enabled=curses.COLORS >= 8)


def _hex_rgb(hex_color: str) -> Optional[tuple[int, int, int]]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return None


def _line_color_idx(key: str) -> Optional[int]:
    """The line's colour as an xterm-256 index, or None."""
    try:
        rgb = _hex_rgb(load_line(key).hex)
    except (ValueError, TypeError):
        return None
    return None if rgb is None else rgb_to_xterm256(*rgb)


# --------------------------------------------------------------------------- #
# Driver (IO at the edges).                                                   #
# --------------------------------------------------------------------------- #


def _resolve_station(line: Line, requested: Optional[str]) -> Station:
    if requested:
        try:
            return find_station(line, requested)
        except (ValueError, TypeError):
            pass
    return line.stations[0]


def _list_pane_width(total_cols: int) -> int:
    width = total_cols // 4
    width = max(_LIST_MIN_W, min(_LIST_MAX_W, width))
    if total_cols - width - 1 < _BOARD_MIN_W:
        width = max(_LIST_MIN_W, total_cols - _BOARD_MIN_W - 1)
    return max(0, width)


def _safe_addstr(
    win: "curses.window",
    row: int,
    col: int,
    text: str,
    attr: int = 0,
) -> None:
    """addstr that never raises on clipping at the screen edge."""
    if not text:
        return
    try:
        win.addstr(row, col, text, attr)
    except curses.error:
        pass


@dataclass
class _TuiState:
    """Mutable driver state for the running TUI."""

    keys: tuple[str, ...]
    labels: dict[str, str]
    selected: int
    filtering: bool
    query: str
    line_key: str
    station_key: str
    favorites: list[tuple[str, str]]
    fav_cursor: int


def _filtered_keys(state: _TuiState) -> tuple[str, ...]:
    return fuzzy_filter(state.keys, state.query, state.labels)


def _current_view_key(state: _TuiState) -> Optional[str]:
    view = _filtered_keys(state)
    if not view:
        return None
    return view[clamp_index(state.selected, len(view))]


def _load_active(state: _TuiState) -> tuple[Optional[Line], Optional[Station]]:
    try:
        line = load_line(state.line_key)
    except (ValueError, TypeError):
        return None, None
    return line, _resolve_station(line, state.station_key)


def _board_rows(
    line: Optional[Line],
    station: Optional[Station],
    board_width: int,
    now: datetime,
) -> Optional[list[str]]:
    """Render the coloured (ANSI) board rows for the active target, or None."""
    if line is None or station is None:
        return None
    try:
        departures, label = get_departures(line, station, now)
        return render.render_board(line, station, departures, board_width, label)
    except Exception:  # never let a render glitch kill the loop
        return None


def _draw_list(
    win: "curses.window",
    state: _TuiState,
    colors: _Colors,
    height: int,
    pal_width: int,
) -> None:
    view = _filtered_keys(state)
    selected = clamp_index(state.selected, len(view))

    header = "/ " + state.query if state.filtering else "Lines"
    _safe_addstr(win, 0, 0, header[:pal_width].ljust(pal_width), curses.A_BOLD)

    body_rows = max(height - 1, 1)
    top = selected - body_rows + 1 if selected >= body_rows else 0

    fav_keys = {lk for lk, _ in state.favorites}
    for row in range(body_rows):
        idx = top + row
        if idx >= len(view):
            break
        key = view[idx]
        symbol = key[:2].upper()
        label = state.labels.get(key, key)
        star = "*" if key in fav_keys else " "
        text = f"{star}{symbol} {label}"[:pal_width].ljust(pal_width)

        attr = colors.attr(_line_color_idx(key), None)
        if idx == selected:
            attr |= curses.A_REVERSE
        _safe_addstr(win, row + 1, 0, text, attr)


def _draw_board_rows(
    win: "curses.window",
    rows: Optional[list[str]],
    origin_col: int,
    height: int,
    board_width: int,
    colors: _Colors,
) -> None:
    """Paint coloured board ``rows`` (ANSI parsed into curses runs)."""
    if rows is None:
        _safe_addstr(win, 0, origin_col, "(no line data)")
        return
    for r, raw in enumerate(rows):
        if r >= height:
            break
        col = 0
        for seg, fg, bg in parse_ansi_runs(raw):
            if col >= board_width:
                break
            attr = colors.attr(fg, bg)
            clipped = ""
            seg_w = 0
            for ch in seg:
                cw = _char_width(ch)
                if col + seg_w + cw > board_width:
                    break
                clipped += ch
                seg_w += cw
            if clipped:
                _safe_addstr(win, r, origin_col + col, clipped, attr)
            col += seg_w


def _draw_help(win: "curses.window", row: int, cols: int) -> None:
    hint = (
        "j/k move  h/l station  Enter select  / filter  "
        "f fav  F next-fav  r refresh  q quit"
    )
    _safe_addstr(win, row, 0, hint[:cols], curses.A_DIM)


def _draw_too_small(win: "curses.window", rows: int, cols: int) -> None:
    win.erase()
    msg = "Terminal too small"
    _safe_addstr(win, max(rows // 2, 0), max((cols - len(msg)) // 2, 0), msg)
    win.noutrefresh()


def _commit_selection(state: _TuiState) -> _TuiState:
    key = _current_view_key(state)
    if key is None:
        return state
    try:
        line = load_line(key)
    except (ValueError, TypeError):
        return state
    return replace(state, line_key=key, station_key=_resolve_station(line, None).id)


def _step_active_station(state: _TuiState, delta: int) -> _TuiState:
    line, station = _load_active(state)
    if line is None or station is None:
        return state
    return replace(state, station_key=step_station_key(line, station, delta))


def _toggle_active_favorite(state: _TuiState) -> _TuiState:
    pair = (state.line_key, state.station_key)
    new_favs = toggle_favorite(state.favorites, pair)
    try:
        save_favorites(new_favs)
    except OSError:
        pass
    return replace(state, favorites=new_favs)


def _jump_favorite(state: _TuiState) -> _TuiState:
    nxt = next_favorite_index(state.favorites, state.fav_cursor)
    if nxt < 0:
        return state
    line_key, station_key = state.favorites[nxt]
    view = fuzzy_filter(state.keys, state.query, state.labels)
    selected = view.index(line_key) if line_key in view else state.selected
    return replace(
        state,
        line_key=line_key,
        station_key=station_key,
        fav_cursor=nxt,
        selected=selected,
    )


def _move_selection(state: _TuiState, delta: int) -> _TuiState:
    view = _filtered_keys(state)
    return replace(state, selected=clamp_index(state.selected + delta, len(view)))


def _handle_filter_key(state: _TuiState, key: int) -> _TuiState:
    if key in (curses.KEY_ENTER, 10, 13):
        return replace(state, filtering=False)
    if key == 27:
        return replace(state, filtering=False, query="")
    if key in (curses.KEY_BACKSPACE, 127, 8):
        return replace(state, query=state.query[:-1], selected=0)
    if 32 <= key < 127:
        return replace(state, query=state.query + chr(key), selected=0)
    return state


def _handle_key(state: _TuiState, key: int) -> tuple[_TuiState, bool]:
    if state.filtering:
        return _handle_filter_key(state, key), True
    if key in (ord("q"), ord("Q")):
        return state, False
    if key in (curses.KEY_UP, ord("k")):
        return _move_selection(state, -1), True
    if key in (curses.KEY_DOWN, ord("j")):
        return _move_selection(state, +1), True
    if key in (curses.KEY_LEFT, ord("h")):
        return _step_active_station(state, -1), True
    if key in (curses.KEY_RIGHT, ord("l")):
        return _step_active_station(state, +1), True
    if key in (curses.KEY_ENTER, 10, 13):
        return _commit_selection(state), True
    if key == ord("/"):
        return replace(state, filtering=True, query=""), True
    if key == ord("f"):
        return _toggle_active_favorite(state), True
    if key == ord("F"):
        return _jump_favorite(state), True
    if key in (ord("r"), ord("R")):
        return state, True
    return state, True


def _initial_state(config: Config, line_key: str, station_key: str) -> _TuiState:
    keys = tuple(available_lines())
    labels = line_labels(keys)
    selected = keys.index(line_key) if line_key in keys else 0
    return _TuiState(
        keys=keys,
        labels=labels,
        selected=selected,
        filtering=False,
        query="",
        line_key=line_key,
        station_key=station_key,
        favorites=load_favorites(),
        fav_cursor=-1,
    )


def _geometry(stdscr: "curses.window") -> Optional[tuple[int, int, int, int, int, int]]:
    """Return (rows, cols, pal_w, board_col, board_w, body_h) or None if tiny."""
    rows, cols = stdscr.getmaxyx()
    if rows < _MIN_ROWS or cols < _MIN_COLS:
        return None
    pal_w = _list_pane_width(cols)
    board_col = pal_w + 1 if pal_w > 0 else 0
    board_w = max(cols - board_col, _BOARD_MIN_W)
    body_h = rows - 1
    return rows, cols, pal_w, board_col, board_w, body_h


def _paint(
    stdscr: "curses.window",
    state: _TuiState,
    colors: _Colors,
    board_rows: Optional[list[str]],
) -> None:
    """Paint one frame: list pane + (possibly mid-flap) board rows + help."""
    stdscr.erase()
    geom = _geometry(stdscr)
    if geom is None:
        rows, cols = stdscr.getmaxyx()
        _draw_too_small(stdscr, rows, cols)
        curses.doupdate()
        return
    rows, cols, pal_w, board_col, board_w, body_h = geom
    if pal_w > 0:
        _draw_list(stdscr, state, colors, body_h, pal_w)
    _draw_board_rows(stdscr, board_rows, board_col, body_h, board_w, colors)
    _draw_help(stdscr, rows - 1, cols)
    stdscr.noutrefresh()
    curses.doupdate()


def _loop(stdscr: "curses.window", config: Config, state: _TuiState) -> int:
    """Main curses event loop. Returns a process exit code."""
    curses.curs_set(0)
    stdscr.keypad(True)
    colors = _init_colors(config.color)

    last_sig: Optional[tuple[str, str]] = None
    anim: list[list[str]] = []  # remaining flap frames (each a list of rows)

    while True:
        geom = _geometry(stdscr)
        board_w = geom[4] if geom else _BOARD_MIN_W
        line, station = _load_active(state)
        sig = (state.line_key, state.station_key)
        live_rows = _board_rows(line, station, board_w, datetime.now())

        # Target changed -> kick off a split-flap intro toward the new board.
        if sig != last_sig:
            last_sig = sig
            if live_rows is not None:
                anim = list(flap.flap_frames(live_rows, steps=_FLAP_STEPS))

        if anim:
            frame = anim.pop(0)
            _paint(stdscr, state, colors, frame)
            stdscr.timeout(_FLAP_MS)
        else:
            _paint(stdscr, state, colors, live_rows)
            stdscr.timeout(_REFRESH_MS)

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1
        if key in (curses.KEY_RESIZE, -1):
            continue
        state, keep_running = _handle_key(state, key)
        if not keep_running:
            return 0


def run_tui(
    line_key: Optional[str] = None,
    station_key: Optional[str] = None,
    config: Optional[Config] = None,
) -> int:
    """Launch the interactive curses TUI. Returns a process exit code."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    cfg = config if config is not None else load_config()
    resolved_line = line_key or cfg.line
    resolved_station = station_key or cfg.station

    available = available_lines()
    if not available:
        print("jrboard: no line data found.", file=sys.stderr)
        return 1
    if resolved_line not in available:
        resolved_line = available[0]

    try:
        line = load_line(resolved_line)
    except (ValueError, TypeError) as exc:
        print(f"jrboard: {exc}", file=sys.stderr)
        return 2
    resolved_station = _resolve_station(line, resolved_station).id

    state = _initial_state(cfg, resolved_line, resolved_station)

    try:
        return curses.wrapper(lambda scr: _loop(scr, cfg, state))
    except curses.error as exc:
        print(f"jrboard: TUI error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
