"""Interactive curses TUI for jrboard.

A two-pane terminal UI:

* **Left pane** -- a scrollable, fuzzy-filterable list of every available line
  (``available_lines()``), each shown as ``symbol  name_jp`` in the line's own
  colour.
* **Right pane** -- the live departure board (:func:`render.render_board`) for
  the currently selected line + station, re-rendered periodically so the
  departures stay current.

Design split:

* All decision logic (fuzzy filtering, station stepping with loop wrap,
  favourite toggling, selection clamping) lives in **pure functions** that take
  and return plain values, so they are unit-testable without a TTY.
* Everything that touches :mod:`curses`, the clock, or persistence is confined
  to :func:`run_tui` and its private ``_TuiState`` driver. The driver never
  raises out of the event loop: terminal-too-small and resize conditions are
  handled gracefully.
"""

from __future__ import annotations

import curses
import locale
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Optional, Sequence

from . import render
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
from .width import strip_ansi

__all__ = [
    "run_tui",
    "fuzzy_filter",
    "clamp_index",
    "step_station_key",
    "toggle_favorite",
    "next_favorite_index",
    "FilterState",
]

# Periodic re-render cadence (milliseconds) -> curses input timeout.
_REFRESH_MS = 1000

# Minimum usable geometry; below this we show a friendly hint instead of a
# broken layout.
_MIN_COLS = 30
_MIN_ROWS = 8

# Left list pane sizing.
_LIST_MIN_W = 16
_LIST_MAX_W = 28
_BOARD_MIN_W = render._MIN_WIDTH  # reuse the renderer's own floor


# --------------------------------------------------------------------------- #
# Pure helpers (no curses / no IO) -- unit-tested in tests/test_tui.py.        #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FilterState:
    """Result of applying a fuzzy filter to the line list.

    ``keys`` is the surviving subset of line keys (order preserved) and
    ``selected`` is a valid index into ``keys`` (or ``-1`` when empty).
    """

    keys: tuple[str, ...]
    selected: int


def _subsequence_match(needle: str, haystack: str) -> bool:
    """Return True if ``needle`` is a subsequence of ``haystack``.

    Both inputs are compared case-insensitively. An empty needle matches
    everything. This is the classic fuzzy-find rule: the characters of
    ``needle`` must appear in ``haystack`` in order, but not necessarily
    contiguously.
    """
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
    """Return the subset of ``keys`` matching ``query`` as a fuzzy subsequence.

    Matching is attempted against the key itself and, when provided, the
    human label in ``labels`` (e.g. the Japanese name) so a user can filter by
    either. Order from ``keys`` is preserved. An empty/whitespace query returns
    every key unchanged.
    """
    q = query.strip()
    if not q:
        return tuple(keys)
    out: list[str] = []
    for key in keys:
        label = labels.get(key, "") if labels else ""
        if _subsequence_match(q, key) or (
            label and _subsequence_match(q, label)
        ):
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
    """Return the station key one step from ``current`` along ``line``.

    ``delta`` is ``-1`` for previous, ``+1`` for next. Loop lines wrap at the
    ends (delegated to :func:`model.neighbors`); on a non-loop line stepping
    past an endpoint leaves the current station unchanged. The returned key is
    the station ``id``, which :func:`model.find_station` accepts.
    """
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
    """Return a new favourites list with ``pair`` toggled.

    If ``pair`` is already present it is removed; otherwise it is appended.
    The input is never mutated (immutability): a fresh list is returned.
    """
    favs = list(favorites)
    if pair in favs:
        return [fav for fav in favs if fav != pair]
    return favs + [pair]


def next_favorite_index(
    favorites: Sequence[tuple[str, str]],
    current_index: int,
) -> int:
    """Return the next index to cycle to in ``favorites`` (wrapping).

    Returns ``-1`` when there are no favourites. ``current_index`` may be any
    integer (including ``-1`` for "nothing selected yet").
    """
    count = len(favorites)
    if count == 0:
        return -1
    return (current_index + 1) % count


def line_labels(keys: Sequence[str]) -> dict[str, str]:
    """Build a ``{key: name_jp}`` label map, skipping lines that fail to load.

    Used both for fuzzy filtering and for the list display. Never raises: a
    line whose JSON is unreadable simply gets no label (and falls back to its
    key in the UI).
    """
    labels: dict[str, str] = {}
    for key in keys:
        try:
            labels[key] = load_line(key).name_jp
        except (ValueError, TypeError):
            continue
    return labels


# --------------------------------------------------------------------------- #
# Curses layer (IO at the edges).                                             #
# --------------------------------------------------------------------------- #


def _resolve_station(line: Line, requested: Optional[str]) -> Station:
    """Find ``requested`` on ``line`` or fall back to its first station."""
    if requested:
        try:
            return find_station(line, requested)
        except (ValueError, TypeError):
            pass
    return line.stations[0]


def _list_pane_width(total_cols: int) -> int:
    """Pick a left-pane width that leaves room for the board."""
    width = total_cols // 4
    width = max(_LIST_MIN_W, min(_LIST_MAX_W, width))
    # Never starve the board pane below its minimum.
    if total_cols - width - 1 < _BOARD_MIN_W:
        width = max(_LIST_MIN_W, total_cols - _BOARD_MIN_W - 1)
    return max(0, width)


@dataclass(frozen=True)
class _Palette:
    """Resolved curses colour-pair ids, keyed by line key."""

    pairs: dict[str, int]
    enabled: bool


def _hex_to_curses_rgb(hex_color: str) -> Optional[tuple[int, int, int]]:
    """Convert ``#rrggbb`` to curses 0-1000 scaled RGB, or ``None``."""
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return None

    def scale(channel: int) -> int:
        return int(round(channel / 255 * 1000))

    return scale(r), scale(g), scale(b)


def _init_palette(use_color: bool, keys: Sequence[str]) -> _Palette:
    """Initialise per-line curses colour pairs where the terminal allows it.

    Falls back gracefully: if colour is disabled or unsupported, an empty
    palette is returned and the caller renders plain text.
    """
    if not use_color or not curses.has_colors():
        return _Palette(pairs={}, enabled=False)
    try:
        curses.start_color()
        curses.use_default_colors()
    except curses.error:
        return _Palette(pairs={}, enabled=False)

    can_change = curses.can_change_color() and curses.COLORS >= 16
    pairs: dict[str, int] = {}
    next_color = 16  # leave the first 16 ANSI slots intact
    next_pair = 1
    for key in keys:
        if next_pair >= curses.COLOR_PAIRS:
            break
        fg = -1
        if can_change and next_color < curses.COLORS:
            rgb = _line_hex(key)
            if rgb is not None:
                try:
                    curses.init_color(next_color, *rgb)
                    fg = next_color
                    next_color += 1
                except curses.error:
                    fg = -1
        try:
            curses.init_pair(next_pair, fg, -1)
        except curses.error:
            continue
        pairs[key] = next_pair
        next_pair += 1
    return _Palette(pairs=pairs, enabled=bool(pairs))


def _line_hex(key: str) -> Optional[tuple[int, int, int]]:
    """Best-effort line colour as curses RGB; ``None`` on any failure."""
    try:
        return _hex_to_curses_rgb(load_line(key).hex)
    except (ValueError, TypeError):
        return None


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
        # Writing the last cell of the last line raises; that's expected.
        pass


@dataclass
class _TuiState:
    """Mutable driver state for the running TUI (kept off the pure layer)."""

    keys: tuple[str, ...]
    labels: dict[str, str]
    selected: int  # index into the *filtered* view
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
    idx = clamp_index(state.selected, len(view))
    return view[idx]


def _load_active(state: _TuiState) -> tuple[Optional[Line], Optional[Station]]:
    """Load the committed (line_key, station_key) board target safely."""
    try:
        line = load_line(state.line_key)
    except (ValueError, TypeError):
        return None, None
    station = _resolve_station(line, state.station_key)
    return line, station


def _draw_list(
    win: "curses.window",
    state: _TuiState,
    palette: _Palette,
    height: int,
    pal_width: int,
) -> None:
    """Render the left line-list pane (header + scrolling list)."""
    view = _filtered_keys(state)
    selected = clamp_index(state.selected, len(view))

    header = "/ " + state.query if state.filtering else "Lines"
    _safe_addstr(win, 0, 0, header[: pal_width].ljust(pal_width), curses.A_BOLD)

    # Vertical scroll so the selection stays visible.
    body_rows = max(height - 1, 1)
    top = 0
    if selected >= body_rows:
        top = selected - body_rows + 1

    fav_keys = {lk for lk, _ in state.favorites}
    for row in range(body_rows):
        idx = top + row
        if idx >= len(view):
            break
        key = view[idx]
        symbol = key[:2].upper()
        label = state.labels.get(key, key)
        star = "*" if key in fav_keys else " "
        text = f"{star}{symbol} {label}"
        text = text[:pal_width].ljust(pal_width)

        attr = 0
        if palette.enabled and key in palette.pairs:
            attr |= curses.color_pair(palette.pairs[key])
        if idx == selected:
            attr |= curses.A_REVERSE
        _safe_addstr(win, row + 1, 0, text, attr)


def _draw_board(
    win: "curses.window",
    line: Optional[Line],
    station: Optional[Station],
    origin_col: int,
    height: int,
    board_width: int,
    now: datetime,
) -> None:
    """Render the right board pane (ANSI stripped, plain curses text)."""
    if line is None or station is None:
        _safe_addstr(win, 0, origin_col, "(no line data)")
        return
    try:
        departures, label = get_departures(line, station, now)
        rows = render.render_board(line, station, departures, board_width, label)
    except Exception as exc:  # never let a render glitch kill the loop
        _safe_addstr(win, 0, origin_col, f"render error: {exc}"[:board_width])
        return
    for r, raw in enumerate(rows):
        if r >= height:
            break
        _safe_addstr(win, r, origin_col, strip_ansi(raw)[:board_width])


def _draw_help(win: "curses.window", row: int, cols: int) -> None:
    """Render the one-line key hint footer."""
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
    """Commit the highlighted line as the active board, resetting station."""
    key = _current_view_key(state)
    if key is None:
        return state
    try:
        line = load_line(key)
    except (ValueError, TypeError):
        return state
    station = _resolve_station(line, None)
    return replace(state, line_key=key, station_key=station.id)


def _step_active_station(state: _TuiState, delta: int) -> _TuiState:
    """Move the active station one step along the active line."""
    line, station = _load_active(state)
    if line is None or station is None:
        return state
    new_key = step_station_key(line, station, delta)
    return replace(state, station_key=new_key)


def _toggle_active_favorite(state: _TuiState) -> _TuiState:
    """Toggle (line_key, station_key) in favourites and persist."""
    pair = (state.line_key, state.station_key)
    new_favs = toggle_favorite(state.favorites, pair)
    try:
        save_favorites(new_favs)
    except OSError:
        pass  # persistence failure must not break the session
    return replace(state, favorites=new_favs)


def _jump_favorite(state: _TuiState) -> _TuiState:
    """Cycle to the next favourite (if any) and make it the active board."""
    nxt = next_favorite_index(state.favorites, state.fav_cursor)
    if nxt < 0:
        return state
    line_key, station_key = state.favorites[nxt]
    # Move the list selection onto the favourite's line when visible.
    view = fuzzy_filter(state.keys, state.query, state.labels)
    selected = state.selected
    if line_key in view:
        selected = view.index(line_key)
    return replace(
        state,
        line_key=line_key,
        station_key=station_key,
        fav_cursor=nxt,
        selected=selected,
    )


def _move_selection(state: _TuiState, delta: int) -> _TuiState:
    view = _filtered_keys(state)
    new_sel = clamp_index(state.selected + delta, len(view))
    return replace(state, selected=new_sel)


def _handle_filter_key(state: _TuiState, key: int) -> _TuiState:
    """Process a keypress while in '/' fuzzy-filter input mode."""
    if key in (curses.KEY_ENTER, 10, 13):
        return replace(state, filtering=False)
    if key == 27:  # ESC cancels the filter
        return replace(state, filtering=False, query="")
    if key in (curses.KEY_BACKSPACE, 127, 8):
        return replace(state, query=state.query[:-1], selected=0)
    if 32 <= key < 127:
        return replace(state, query=state.query + chr(key), selected=0)
    return state


def _handle_key(state: _TuiState, key: int) -> tuple[_TuiState, bool]:
    """Dispatch a keypress to a state transition.

    Returns ``(new_state, keep_running)``. ``keep_running`` is False only for
    the quit key. Filtering mode swallows printable input for the query.
    """
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
        return state, True  # forces a redraw on the next loop tick
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


def _draw(stdscr: "curses.window", state: _TuiState, palette: _Palette) -> None:
    """Paint one full frame; tolerant of tiny terminals."""
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()
    if rows < _MIN_ROWS or cols < _MIN_COLS:
        _draw_too_small(stdscr, rows, cols)
        curses.doupdate()
        return

    pal_w = _list_pane_width(cols)
    board_col = pal_w + 1 if pal_w > 0 else 0
    board_w = max(cols - board_col, _BOARD_MIN_W)
    body_h = rows - 1  # reserve the last row for the help hint

    if pal_w > 0:
        _draw_list(stdscr, state, palette, body_h, pal_w)
    line, station = _load_active(state)
    _draw_board(stdscr, line, station, board_col, body_h, board_w, datetime.now())
    _draw_help(stdscr, rows - 1, cols)

    stdscr.noutrefresh()
    curses.doupdate()


def _loop(stdscr: "curses.window", config: Config, state: _TuiState) -> int:
    """Main curses event loop. Returns a process exit code."""
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.timeout(_REFRESH_MS)
    stdscr.keypad(True)
    palette = _init_palette(config.color, state.keys)

    while True:
        _draw(stdscr, state, palette)
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1
        if key == curses.KEY_RESIZE:
            continue  # next _draw re-reads getmaxyx and re-lays out
        if key == -1:
            continue  # timeout: just re-render so departures stay current
        state, keep_running = _handle_key(state, key)
        if not keep_running:
            return 0


def run_tui(
    line_key: Optional[str] = None,
    station_key: Optional[str] = None,
    config: Optional[Config] = None,
) -> int:
    """Launch the interactive curses TUI. Returns a process exit code.

    ``line_key`` / ``station_key`` override the configured defaults when given.
    ``config`` may be injected (mainly for tests); otherwise it is loaded from
    disk. The function sets up the locale for wide-character output, then hands
    control to :func:`curses.wrapper`, which restores the terminal on exit even
    if an error propagates.
    """
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    cfg = config if config is not None else load_config()
    resolved_line = line_key or cfg.line
    resolved_station = station_key or cfg.station

    available = available_lines()
    if not available:
        print("jrboard: no line data found.", file=__import__("sys").stderr)
        return 1
    if resolved_line not in available:
        resolved_line = available[0]

    # Validate / normalise the station against the chosen line up front so the
    # loop always starts on a real station id.
    try:
        line = load_line(resolved_line)
    except (ValueError, TypeError) as exc:
        print(f"jrboard: {exc}", file=__import__("sys").stderr)
        return 2
    resolved_station = _resolve_station(line, resolved_station).id

    state = _initial_state(cfg, resolved_line, resolved_station)

    try:
        return curses.wrapper(lambda scr: _loop(scr, cfg, state))
    except curses.error as exc:
        print(f"jrboard: TUI error: {exc}", file=__import__("sys").stderr)
        return 1
    except KeyboardInterrupt:
        return 0
