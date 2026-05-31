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

All errors are reported on ``stderr`` and mapped to a non-zero exit code; the
module never leaks a raw traceback to the user.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from typing import Optional, Sequence

from . import flap, render
from .model import Line, Station, available_lines, find_station, load_line
from .sources import Departure, get_departures

# Sensible flagship defaults per line so ``--line X`` alone is useful.
_DEFAULT_STATION: dict[str, str] = {
    "yamanote": "shinjuku",
    "asakusa": "asakusa",
}
_FALLBACK_STATION = "01"  # first station number; valid on every line

_CLEAR_SCREEN = "\033[2J\033[H"  # clear + home cursor
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"

_FLAP_STEPS = 14
_FRAME_DELAY_S = 0.045


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jrboard",
        description=(
            "Terminal split-flap JR / Toei departure board. Renders a full "
            "ANSI board or a single-line statusline marquee."
        ),
    )
    parser.add_argument(
        "--line",
        choices=("yamanote", "asakusa"),
        default="yamanote",
        help="Which line to display (default: yamanote).",
    )
    parser.add_argument(
        "--station",
        default=None,
        help=(
            "Station key: name_en, id, or number. Defaults to a flagship "
            "station for the chosen line."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("board", "statusline"),
        default="board",
        help="Render a full board or a single statusline (default: board).",
    )
    parser.add_argument(
        "--no-flap",
        action="store_true",
        help="Skip the split-flap animation; paint the resolved board.",
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
        "--list",
        dest="list_lines",
        action="store_true",
        help="List available lines and their stations, then exit.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=60,
        help="Board width in columns (default: 60).",
    )
    return parser


def _resolve_station_key(line_key: str, requested: Optional[str]) -> str:
    if requested:
        return requested
    return _DEFAULT_STATION.get(line_key, _FALLBACK_STATION)


def _print_lines(lines: Sequence[str]) -> None:
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _list_lines() -> int:
    """Print available lines and their stations; return an exit code."""
    keys = available_lines()
    if not keys:
        print("No line data found.", file=sys.stderr)
        return 1
    for key in keys:
        try:
            line = load_line(key)
        except ValueError as exc:
            print(f"  ({key}: failed to load: {exc})", file=sys.stderr)
            continue
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


def _animate_board(board_lines: Sequence[str], seed: int) -> None:
    """Play the split-flap animation that resolves into ``board_lines``."""
    targets = list(board_lines)
    for frame in flap.flap_frames(targets, steps=_FLAP_STEPS, seed=seed):
        sys.stdout.write(_CLEAR_SCREEN)
        _print_lines(frame)
        time.sleep(_FRAME_DELAY_S)


def _run_board(args: argparse.Namespace, line: Line, station: Station) -> int:
    width = args.width
    interval = max(args.interval, 0.5)
    use_flap = not args.no_flap
    seed = 0
    hide_cursor = sys.stdout.isatty()

    if hide_cursor:
        sys.stdout.write(_HIDE_CURSOR)
        sys.stdout.flush()
    try:
        while True:
            now = datetime.now()
            departures, label = get_departures(line, station, now)
            board = _render_resolved_board(
                line, station, departures, width, label
            )

            sys.stdout.write(_CLEAR_SCREEN)
            if use_flap:
                _animate_board(board, seed)
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


def _run_statusline(line: Line, station: Station) -> int:
    # Imported lazily so a missing statusline module never breaks board mode.
    from .statusline import statusline_text

    now = datetime.now()
    departures, _label = get_departures(line, station, now, limit=3)
    columns = _terminal_columns()
    text = statusline_text(line, station, departures, now, columns=columns)
    # Exactly one line, no trailing newline.
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns a process exit code (0 on success)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_lines:
        return _list_lines()

    try:
        line = load_line(args.line)
    except ValueError as exc:
        print(f"jrboard: {exc}", file=sys.stderr)
        return 2

    station_key = _resolve_station_key(args.line, args.station)
    try:
        station = find_station(line, station_key)
    except (ValueError, TypeError) as exc:
        print(f"jrboard: {exc}", file=sys.stderr)
        return 2

    if args.mode == "statusline":
        return _run_statusline(line, station)
    return _run_board(args, line, station)


if __name__ == "__main__":  # pragma: no cover - module run convenience
    raise SystemExit(main())
