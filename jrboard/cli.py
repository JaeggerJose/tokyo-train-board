"""Command-line entry point for jrboard.

Wires the data model, departure sources, split-flap animation, board renderer
and statusline marquee together behind an ``argparse`` interface.

Two modes:

``board``
    Clears the screen, plays a split-flap animation that resolves into the
    real departure board, holds, then refreshes on ``--interval``. ``--once``
    renders a single resolved board and exits. ``--no-flap`` skips the
    animation and paints the resolved board directly.

``statusline``
    Prints exactly one line (no trailing newline) and exits, so a Claude Code
    ``statusLine`` command can invoke it on every render; the marquee offset is
    derived from the current time so successive calls advance it.

Additional modes (additive; default mode stays ``board``):

``--tui``
    Launch the interactive curses two-pane browser (delegates to
    :func:`jrboard.tui.run_tui`).

``--pomodoro MIN``
    Reframe a focus timer as a train journey (:mod:`jrboard.journey`): animate a
    split-flap intro, then redraw the journey board each second until arrival.

``--commute``
    Render the commute guardian (:mod:`jrboard.commute`) -- when to leave home
    to catch the next train -- as a board, or a one-liner in statusline mode.

``--feed-ics PATH``
    Use a local ``.ics`` agenda (:func:`jrboard.feeds.departures_from_ics`) as
    the departure source instead of the live/static timetable, labelled
    ``AGENDA``.

All errors are reported on ``stderr`` and mapped to a non-zero exit code; the
module never leaks a raw traceback to the user.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
import time
from datetime import datetime
from typing import Optional, Sequence

from . import config as config_mod
from . import flap, render
from .config import Config
from .model import Line, Station, available_lines, find_station, load_line
from .sources import Departure, get_departures
from .width import get_visual_width

# Responsive (RWD) statusline budgets, in visual columns.
_STATUS_TRAIN_MIN = 24       # keep at least this much for the train marquee
_STATUS_MIN_FOR_TOKENS = 30  # below this width, drop the token gauge entirely
_MINITABLE_LABEL_RESERVE = 16  # space the minitable header keeps for badge+station

# Sensible flagship defaults per line so ``--line X`` alone is useful.
_DEFAULT_STATION: dict[str, str] = {
    "yamanote": "shinjuku",
    "asakusa": "asakusa",
}
_FALLBACK_STATION = "01"  # first station number; valid on every line

_CLEAR_SCREEN = "\033[2J\033[H"  # clear + home cursor
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"

# Slower, more mechanical settle by default (~22 * 0.08s ≈ 1.8s). Override at
# runtime with --flap-steps / --flap-delay to tune the feel.
_FLAP_STEPS = 22
_FRAME_DELAY_S = 0.08


def _build_parser(config: Config) -> argparse.ArgumentParser:
    """Build the argument parser, seeding defaults from ``config``.

    Every default is drawn from the loaded :class:`Config` so the config file
    sets the baseline; an explicit CLI flag always overrides it.
    """
    parser = argparse.ArgumentParser(
        prog="jrboard",
        description=(
            "Terminal split-flap JR / Toei departure board. Renders a full "
            "ANSI board, a single-line statusline marquee, an interactive "
            "curses browser (--tui), a focus-timer train journey (--pomodoro), "
            "or a commute guardian (--commute)."
        ),
    )
    parser.add_argument(
        "--line",
        choices=tuple(available_lines()) or ("yamanote",),
        default=config.line,
        help=f"Which line to display (config/default: {config.line}).",
    )
    parser.add_argument(
        "--station",
        default=None,
        help=(
            "Station key: name_en, id, or number. Defaults to the configured "
            "station, then a flagship station for the chosen line."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("board", "statusline", "minitable"),
        default="board",
        help=(
            "Render a full board, a single-line statusline marquee, or a "
            "multi-line minitable (default: board)."
        ),
    )
    parser.add_argument(
        "--no-flap",
        action="store_true",
        help="Skip the split-flap animation; paint the resolved board.",
    )
    parser.add_argument(
        "--flap-steps",
        dest="flap_steps",
        type=int,
        default=config.flap_steps,
        help=(
            "Split-flap frames from scramble to resolved "
            f"(config/default: {config.flap_steps}). Higher = more gradual."
        ),
    )
    parser.add_argument(
        "--flap-delay",
        dest="flap_delay",
        type=float,
        default=config.flap_delay,
        help=(
            "Seconds held per flap frame "
            f"(config/default: {config.flap_delay}). Higher = slower."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Render once and exit (no refresh loop).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between board refreshes (default: 10).",
    )
    parser.add_argument(
        "--rotate",
        type=float,
        nargs="?",
        const=5.0,
        default=None,
        metavar="MIN",
        help=(
            "Board mode: every MIN minutes (default 5) jump to a RANDOM line "
            "and station — a screensaver-style tour of the whole network. "
            "Statusline/minitable mode: time-bucketed rotation through the "
            "(city-scoped) pool every MIN minutes (default 0.5 when given "
            "with no value), so successive renders advance the line."
        ),
    )
    parser.add_argument(
        "--list",
        dest="list_lines",
        action="store_true",
        help="List available lines and their stations, then exit.",
    )
    parser.add_argument(
        "--city",
        default=None,
        help=(
            "Filter to a city (e.g. Tokyo, Osaka, Kyoto, Sapporo, Otaru): "
            "scopes --list and the --rotate random tour."
        ),
    )
    parser.add_argument(
        "--width",
        type=int,
        default=config.width,
        help=f"Board width in columns (config/default: {config.width}).",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=0,
        help=(
            "Statusline mode: force the marquee width (visual columns). Needed "
            "for Claude Code statusLine, which runs without a TTY so the width "
            "cannot be auto-detected. 0 = auto-detect / no marquee."
        ),
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        help="Statusline mode: emit plain text (no line-colour ANSI).",
    )
    parser.add_argument(
        "--scroll-all",
        dest="scroll_all",
        action="store_true",
        help=(
            "Statusline mode: scroll the whole line as a marquee instead of "
            "pinning the station name and scrolling only the departures."
        ),
    )
    parser.add_argument(
        "--claude-stdin",
        dest="claude_stdin",
        action="store_true",
        help=(
            "Statusline/minitable: read the Claude Code JSON blob from STDIN "
            "(when data is piped in) and use it for line selection and the "
            "--tokens gauge. Safe to pass without a pipe (just ignored)."
        ),
    )
    parser.add_argument(
        "--by-session",
        dest="by_session",
        action="store_true",
        help=(
            "Statusline/minitable: pick the line deterministically from the "
            "Claude session id (needs --claude-stdin). Same session always "
            "maps to the same line; scoped by --city. Falls back to --rotate "
            "or the configured default when no session id is present."
        ),
    )
    parser.add_argument(
        "--tokens",
        action="store_true",
        help=(
            "Statusline/minitable: append a compact token-budget gauge "
            "(5h session limit, 7d weekly limit, ctx) parsed from the Claude "
            "STDIN blob. Implies reading STDIN; pair with --claude-stdin."
        ),
    )

    # --- Additive feature flags ------------------------------------------- #
    parser.add_argument(
        "--tui",
        action="store_true",
        help=(
            "Launch the interactive curses browser (two-pane line picker + "
            "live board). Ignores --mode."
        ),
    )
    parser.add_argument(
        "--pomodoro",
        dest="pomodoro",
        type=float,
        default=None,
        metavar="MIN",
        help=(
            "Run a focus timer as a train journey for MIN minutes on --line "
            "(uses --from/--to if given, else auto-picks stations). Animates "
            "in, then redraws each second until arrival. Respects --once."
        ),
    )
    parser.add_argument(
        "--from",
        dest="origin",
        default=None,
        help="Pomodoro origin station key (defaults to a sensible endpoint).",
    )
    parser.add_argument(
        "--to",
        dest="dest",
        default=None,
        help="Pomodoro destination station key (defaults to a sensible stop).",
    )
    parser.add_argument(
        "--commute",
        action="store_true",
        help=(
            "Render the commute guardian (when to leave for the next train). "
            "Needs [commute] home/work in the config. board mode = full board, "
            "statusline mode = one line."
        ),
    )
    parser.add_argument(
        "--feed-ics",
        dest="feed_ics",
        default=None,
        metavar="PATH",
        help=(
            "Use a local .ics agenda file as the departure source (labelled "
            "AGENDA) instead of the timetable, in board/statusline modes."
        ),
    )

    # --- One-shot setup helpers ------------------------------------------- #
    parser.add_argument(
        "--install-statusline",
        dest="install_statusline",
        action="store_true",
        help=(
            "Wire the board into Claude Code's statusLine (~/.claude/"
            "settings.json) and exit. Uses 'python -m jrboard' so it works "
            "without PATH/csl. Respects --columns/--line/--station/--city/"
            "--mode minitable to shape the installed command."
        ),
    )
    parser.add_argument(
        "--uninstall-statusline",
        dest="uninstall_statusline",
        action="store_true",
        help="Remove jrboard's statusLine entry from settings.json and exit.",
    )
    parser.add_argument(
        "--install-csl-theme",
        dest="install_csl_theme",
        nargs="?",
        const="jr-board",
        default=None,
        metavar="NAME",
        help=(
            "Copy a bundled csl theme (default 'jr-board'; also 'jr-timetable') "
            "into ~/.config/csl/themes and exit -- no clone, no manual cp. Then "
            "run 'csl set <NAME>' to activate."
        ),
    )
    return parser


def _resolve_station_key(
    line_key: str, requested: Optional[str], configured: Optional[str] = None
) -> str:
    if requested:
        return requested
    if configured:
        return configured
    return _DEFAULT_STATION.get(line_key, _FALLBACK_STATION)


def _default_station_for(line: Line) -> Optional[Station]:
    """Pick a stable, sensible station for an auto-selected line.

    Prefers the configured flagship for the line key, otherwise the middle
    station (deterministic, so by-session selection stays stable). Returns
    ``None`` only for a line with no stations.
    """
    flagship_key = _DEFAULT_STATION.get(line.key)
    if flagship_key:
        flagship = _optional_station(line, flagship_key)
        if flagship is not None:
            return flagship
    if not line.stations:
        return None
    return line.stations[len(line.stations) // 2]


def _print_lines(lines: Sequence[str]) -> None:
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _list_lines(city_filter: Optional[str] = None) -> int:
    """Print available lines grouped by city; return an exit code."""
    keys = available_lines()
    if not keys:
        print("No line data found.", file=sys.stderr)
        return 1

    groups: dict[str, list[Line]] = {}
    for key in keys:
        try:
            line = load_line(key)
        except ValueError as exc:
            print(f"  ({key}: failed to load: {exc})", file=sys.stderr)
            continue
        groups.setdefault(line.city, []).append(line)

    # Tokyo first (the original network), then the rest alphabetically.
    cities = sorted(groups, key=lambda c: (c != "Tokyo", c))
    if city_filter:
        want = city_filter.strip().lower()
        cities = [c for c in cities if c.lower() == want]
        if not cities:
            available = ", ".join(sorted(groups))
            print(f"jrboard: no city matching '{city_filter}'. "
                  f"Available: {available}", file=sys.stderr)
            return 2

    for city in cities:
        print(f"\n== {city} ==")
        for line in groups[city]:
            loop = "loop" if line.loop else "linear"
            print(f"{line.symbol}  {line.key}  ({line.name_jp} / {line.name_en}) "
                  f"[{loop}, {len(line.stations)} stations]")
            for st in line.stations:
                print(f"    {st.number:>3}  {st.name_en:<20} {st.name_jp}")
    return 0


def _render_resolved_board(
    line: Line,
    station: Station,
    departures: Sequence[Departure],
    width: int,
    source_label: str,
) -> list[str]:
    return render.render_board(line, station, departures, width, source_label)


def _animate_board(
    board_lines: Sequence[str],
    seed: int,
    steps: int = _FLAP_STEPS,
    delay: float = _FRAME_DELAY_S,
) -> None:
    """Play the split-flap animation that resolves into ``board_lines``."""
    targets = list(board_lines)
    steps = max(1, steps)
    delay = max(0.0, delay)
    for frame in flap.flap_frames(targets, steps=steps, seed=seed):
        sys.stdout.write(_CLEAR_SCREEN)
        _print_lines(frame)
        time.sleep(delay)


def _departures_for(
    line: Line,
    station: Station,
    now: datetime,
    limit: int,
    feed_ics: Optional[str],
) -> tuple[list[Departure], str]:
    """Return ``(departures, label)`` from the agenda feed or the timetable.

    When ``feed_ics`` is given, the local ``.ics`` agenda is used (label
    ``AGENDA``); ``feeds.departures_from_ics`` never raises and returns ``[]``
    on a missing/unreadable/empty file. Otherwise the normal timetable source
    is used, preserving its ``ODPT``/``STATIC`` provenance label.
    """
    if feed_ics:
        from .feeds import departures_from_ics

        return departures_from_ics(feed_ics, now, limit), "AGENDA"
    return get_departures(line, station, now, limit)


def _random_target(
    city: Optional[str] = None,
) -> tuple[Optional[Line], Optional[Station]]:
    """Pick a random (line, station), optionally scoped to ``city``."""
    keys = available_lines()
    if not keys:
        return None, None
    if city:
        want = city.strip().lower()
        scoped: list[str] = []
        for key in keys:
            try:
                if load_line(key).city.lower() == want:
                    scoped.append(key)
            except (ValueError, TypeError):
                continue
        keys = scoped or keys
    try:
        line = load_line(random.choice(keys))
    except (ValueError, TypeError):
        return None, None
    if not line.stations:
        return line, None
    return line, random.choice(line.stations)


def _run_board(args: argparse.Namespace, line: Line, station: Station) -> int:
    width = args.width
    interval = max(args.interval, 0.5)
    use_flap = not args.no_flap
    seed = 0
    feed_ics = getattr(args, "feed_ics", None)
    rotate_min = getattr(args, "rotate", None)
    rotate_secs = rotate_min * 60 if rotate_min and rotate_min > 0 else None
    # Rotate immediately on the first frame so --city takes effect at once
    # (otherwise the initial board would show the global default for one whole
    # interval before the first jump).
    next_rotate = time.monotonic() if rotate_secs else None
    hide_cursor = sys.stdout.isatty()

    if hide_cursor:
        sys.stdout.write(_HIDE_CURSOR)
        sys.stdout.flush()
    try:
        while True:
            # Screensaver tour: jump to a random line/station when due.
            if next_rotate is not None and time.monotonic() >= next_rotate:
                rline, rstation = _random_target(getattr(args, "city", None))
                if rline is not None and rstation is not None:
                    line, station = rline, rstation
                next_rotate = time.monotonic() + rotate_secs

            now = datetime.now()
            departures, label = _departures_for(
                line, station, now, 6, feed_ics
            )
            board = _render_resolved_board(
                line, station, departures, width, label
            )

            sys.stdout.write(_CLEAR_SCREEN)
            if use_flap:
                _animate_board(board, seed, args.flap_steps, args.flap_delay)
                seed += 1
            sys.stdout.write(_CLEAR_SCREEN)
            _print_lines(board)

            if args.once:
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
    finally:
        if hide_cursor:
            sys.stdout.write(_SHOW_CURSOR)
            sys.stdout.flush()


def _run_statusline(
    line: Line,
    station: Station,
    pin_label: bool = True,
    columns: int = 0,
    color: bool = True,
    feed_ics: Optional[str] = None,
    minitable: bool = False,
    token_pcts: Optional[tuple] = None,
) -> int:
    # Imported lazily so a missing statusline module never breaks board mode.
    from .claude_input import token_gauge
    from .statusline import minitable_text, statusline_text

    now = datetime.now()
    departures, _label = _departures_for(line, station, now, 3, feed_ics)
    # An explicit --columns wins; otherwise fall back to TTY auto-detection.
    columns = columns if columns and columns > 0 else _terminal_columns()

    sess, wk, ctx = (token_pcts or (None, None, None))
    have_tok = token_pcts is not None and any(p is not None for p in token_pcts)
    bounded = bool(columns and columns > 0)

    if minitable:
        # Fit the gauge into the header's spare width (drops ctx -> 7d -> 5h).
        budget = max(0, columns - _MINITABLE_LABEL_RESERVE) if bounded else 0
        tok = token_gauge(sess, wk, ctx, color=color, max_width=budget) if have_tok else ""
        text = minitable_text(
            line, station, departures, now,
            columns=columns, color=color, token_seg=tok,
        )
    else:
        # RWD marquee: reserve the train, give the gauge the remaining width and
        # let it shrink (ctx -> 7d -> 5h); drop it entirely when too narrow.
        tok = ""
        if have_tok:
            if not bounded:
                tok = token_gauge(sess, wk, ctx, color=color)  # unbounded
            elif columns >= _STATUS_MIN_FOR_TOKENS:
                spare = max(0, columns - _STATUS_TRAIN_MIN)
                tok = token_gauge(sess, wk, ctx, color=color, max_width=spare)
        tok_w = get_visual_width(tok) if tok else 0
        body_cols = columns - tok_w - 1 if (bounded and tok) else columns
        text = statusline_text(
            line, station, departures, now,
            columns=body_cols, pin_label=pin_label, color=color,
        )
        if tok:
            # Tokens go on the LEFT: the statusLine has no pane width, and
            # Claude Code truncates the line from the RIGHT to fit the pane, so
            # leading with the gauge keeps 5h/7d/ctx visible even in a narrow
            # split — the (less critical) scrolling departures get clipped first.
            text = f"{tok} {text}"
    # No trailing newline (one line for statusline, several for minitable).
    sys.stdout.write(text)
    sys.stdout.flush()
    return 0


def _terminal_columns() -> int:
    """Best-effort terminal width; ``0`` means 'do not marquee'."""
    env_cols = os.environ.get("COLUMNS")
    if env_cols:
        try:
            return max(int(env_cols), 0)
        except ValueError:
            pass
    try:
        return shutil.get_terminal_size(fallback=(0, 0)).columns
    except Exception:
        return 0


def _optional_station(line: Line, key: Optional[str]) -> Optional[Station]:
    """Resolve ``key`` on ``line`` to a Station, or ``None`` when absent/bad."""
    if not key:
        return None
    try:
        return find_station(line, key)
    except (ValueError, TypeError):
        return None


def _run_pomodoro(args: argparse.Namespace, line: Line) -> int:
    """Run a focus timer as a train journey on ``line``.

    Builds a single immutable :class:`~jrboard.journey.Journey` (re-rendered
    each tick), plays the split-flap intro once, then redraws every second
    until arrival. ``--once`` renders a single resolved frame and exits. All
    clock reads and sleeping happen here, never in :mod:`jrboard.journey`.
    """
    from . import journey as journey_mod

    duration_min = max(0.0, float(args.pomodoro))
    origin = _optional_station(line, getattr(args, "origin", None))
    dest = _optional_station(line, getattr(args, "dest", None))
    width = args.width

    start = time.time()
    journey = journey_mod.make_journey(
        line,
        origin=origin,
        dest=dest,
        start_epoch=start,
        duration_min=int(round(duration_min)),
    )

    use_flap = not args.no_flap
    hide_cursor = sys.stdout.isatty()
    if hide_cursor:
        sys.stdout.write(_HIDE_CURSOR)
        sys.stdout.flush()
    try:
        if use_flap and not args.once:
            intro = journey_mod.render_journey(journey, time.time(), width)
            sys.stdout.write(_CLEAR_SCREEN)
            _animate_board(intro, seed=0, steps=args.flap_steps,
                           delay=args.flap_delay)

        while True:
            now_epoch = time.time()
            board = journey_mod.render_journey(journey, now_epoch, width)
            sys.stdout.write(_CLEAR_SCREEN)
            _print_lines(board)

            if args.once:
                return 0
            if journey_mod.remaining_sec(journey, now_epoch) <= 0:
                return 0
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0
    finally:
        if hide_cursor:
            sys.stdout.write(_SHOW_CURSOR)
            sys.stdout.flush()


def _run_commute(args: argparse.Namespace, cfg: Config) -> int:
    """Render the commute guardian as a board or a statusline one-liner."""
    from .commute import commute_advice, commute_oneline, render_commute

    now = datetime.now()
    advice = commute_advice(cfg, now)

    if args.mode == "statusline":
        sys.stdout.write(commute_oneline(advice, now))
        sys.stdout.flush()
        return 0

    _print_lines(render_commute(advice, now, width=args.width))
    return 0


def _read_claude_stdin(enabled: bool) -> "Optional[object]":
    """Read+parse the Claude STDIN blob when ``enabled`` and data is present.

    Returns a ``ClaudeStatus`` (possibly all-``None``) or ``None`` when reading
    is disabled or STDIN is an interactive TTY with nothing piped in. Never
    raises: any read failure degrades to ``None``.
    """
    if not enabled:
        return None
    from .claude_input import parse_claude_status

    try:
        # Skip an interactive terminal (no blob is being piped in).
        if sys.stdin is None or sys.stdin.isatty():
            return None
        raw = sys.stdin.read()
    except Exception:
        return None
    return parse_claude_status(raw)


def _select_statusline_target(
    args: argparse.Namespace,
    cfg: Config,
    status: "Optional[object]",
) -> "tuple[Optional[Line], Optional[Station], Optional[str]]":
    """Resolve the (line, station) for statusline/minitable rendering.

    Precedence: explicit --line/--station > --by-session > --rotate >
    config/default. --city scopes the by-session/rotate pool. Returns the
    resolved ``(line, station, error)`` where ``error`` is a user message and
    the line/station are ``None`` on failure.
    """
    from .claude_input import (
        pick_by_rotation,
        pick_by_session,
        scope_keys_by_city,
    )

    # Treat an explicit --line (differing from config) OR an explicit
    # --station as a manual override that wins over by-session/rotate.
    manual = (args.line != cfg.line) or bool(args.station)

    session_id = getattr(status, "session_id", None) if status else None
    rotate_min = getattr(args, "rotate", None)
    by_session = getattr(args, "by_session", False)

    # Period for time-bucketed rotation: --rotate value (minutes) * 60, or 30s
    # (0.5 min) when --rotate is given with no value.
    period = int(rotate_min * 60) if (rotate_min and rotate_min > 0) else 30

    auto_key: Optional[str] = None
    if not manual and (by_session or rotate_min is not None):
        pool = scope_keys_by_city(available_lines(), getattr(args, "city", None))
        if pool:
            if by_session and session_id:
                auto_key = pick_by_session(pool, session_id)
            elif rotate_min is not None:
                auto_key = pick_by_rotation(pool, time.time(), period)
            else:
                # --by-session requested but no session id available and no
                # --rotate fallback: deterministic first of the scoped pool.
                auto_key = pool[0]

    if auto_key is not None:
        try:
            line = load_line(auto_key)
        except ValueError as exc:
            return None, None, str(exc)
        station = _default_station_for(line)
        if getattr(args, "station", None):
            chosen = _optional_station(line, args.station)
            if chosen is not None:
                station = chosen
        if station is None:
            return None, None, f"line {auto_key!r} has no stations"
        return line, station, None

    # Manual / config / default path.
    try:
        line = load_line(args.line)
    except ValueError as exc:
        return None, None, str(exc)
    configured_station = cfg.station if args.line == cfg.line else None
    station_key = _resolve_station_key(
        args.line, args.station, configured_station
    )
    try:
        station = find_station(line, station_key)
    except (ValueError, TypeError) as exc:
        return None, None, str(exc)
    return line, station, None


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns a process exit code (0 on success)."""
    cfg = config_mod.load_config()
    parser = _build_parser(cfg)
    args = parser.parse_args(argv)

    if args.list_lines:
        return _list_lines(args.city)

    # One-shot setup helpers: wire/unwire the Claude Code statusLine, then exit.
    if getattr(args, "install_csl_theme", None) is not None:
        from .install import install_csl_theme

        ok, msg = install_csl_theme(args.install_csl_theme)
        print(f"jrboard: {msg}", file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if getattr(args, "uninstall_statusline", False):
        from .install import uninstall_statusline

        ok, msg = uninstall_statusline()
        print(f"jrboard: {msg}", file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1
    if getattr(args, "install_statusline", False):
        from .install import install_statusline, statusline_command

        cols = args.columns if args.columns and args.columns > 0 else 80
        pinned = args.line if args.line != cfg.line else None
        # Clone install (run as `python3 .../main.py`): emit a script-path command
        # since the package is not importable via `-m jrboard`. Console-script /
        # `-m` invocations keep the PATH-independent `-m jrboard` form.
        invoked = sys.argv[0] or ""
        script = (
            os.path.abspath(invoked)
            if invoked.endswith("main.py") and os.path.isfile(invoked)
            else None
        )
        command = statusline_command(
            columns=cols,
            minitable=(args.mode == "minitable"),
            line=pinned,
            station=(args.station if pinned else None),
            city=args.city,
            script=script,
        )
        ok, msg = install_statusline(command)
        stream = sys.stdout if ok else sys.stderr
        print(f"jrboard: {msg}", file=stream)
        print(f"  statusLine command: {command}", file=stream)
        if ok:
            print("  restart Claude Code (or trigger a render) to see it.",
                  file=stream)
        return 0 if ok else 1

    # --tui: hand the whole terminal to curses (never inside a curses session).
    if args.tui:
        from .tui import run_tui

        return run_tui(
            line_key=args.line, station_key=args.station, config=cfg
        )

    # --commute: independent of a specific board station; uses config home/work.
    if args.commute:
        return _run_commute(args, cfg)

    # Statusline / minitable: support Claude STDIN, by-session/rotate selection
    # and the token gauge. Reading STDIN is enabled by --claude-stdin or
    # implied by --tokens (which needs the blob to populate the gauge).
    if args.mode in ("statusline", "minitable"):
        want_stdin = args.claude_stdin or args.tokens or args.by_session
        status = _read_claude_stdin(want_stdin)

        line, station, err = _select_statusline_target(args, cfg, status)
        if err or line is None or station is None:
            print(f"jrboard: {err or 'could not resolve a line/station'}",
                  file=sys.stderr)
            return 2

        token_pcts = None
        if args.tokens:
            token_pcts = (
                getattr(status, "session_pct", None),
                getattr(status, "weekly_pct", None),
                getattr(status, "ctx_pct", None),
            )

        return _run_statusline(
            line, station,
            pin_label=not args.scroll_all,
            columns=args.columns,
            color=not args.no_color,
            feed_ics=getattr(args, "feed_ics", None),
            minitable=(args.mode == "minitable"),
            token_pcts=token_pcts,
        )

    try:
        line = load_line(args.line)
    except ValueError as exc:
        print(f"jrboard: {exc}", file=sys.stderr)
        return 2

    # --pomodoro only needs the line (stations auto-picked or via --from/--to).
    if args.pomodoro is not None:
        return _run_pomodoro(args, line)

    # The configured station belongs to the configured line; only honour it as
    # a default when the user did not switch lines, otherwise fall back to the
    # flagship station for the chosen line.
    configured_station = cfg.station if args.line == cfg.line else None
    station_key = _resolve_station_key(
        args.line, args.station, configured_station
    )
    try:
        station = find_station(line, station_key)
    except (ValueError, TypeError) as exc:
        print(f"jrboard: {exc}", file=sys.stderr)
        return 2

    return _run_board(args, line, station)


if __name__ == "__main__":  # pragma: no cover - module run convenience
    raise SystemExit(main())
