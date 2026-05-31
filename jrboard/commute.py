"""Commute guardian: when to leave home to catch the train (pure logic).

Given a configured ``home`` and ``work`` station (each a ``(line_key,
station_key)`` pair) and the current time, this module decides the relevant
travel direction -- ``home -> work`` in the morning, ``work -> home`` in the
afternoon/evening -- resolves the boarding station and the matching departure
direction on its line, fetches upcoming departures, and computes how many
minutes until the user must *leave* to still catch the soonest reachable train
(accounting for ``leave_buffer_min`` walk-to-station time).

Design constraints (mirrors the rest of jrboard):
- Value objects are frozen dataclasses; nothing is mutated in place.
- The time-of-day threshold is a small injectable helper so it is testable
  without real clocks.
- Rendering is kept separate from the decision logic; rendering never raises
  on degraded input.
- The heavy lifting (line loading, departure sourcing) is injected so the
  decision logic can be exercised with fakes in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Sequence

from . import width as _w
from .model import Line, Station, find_station, load_line
from .render import _clamp_width, _frame_div, _frame_top, _row  # frame helpers
from .sources import Departure, get_departures

__all__ = [
    "CommuteAdvice",
    "is_morning",
    "resolve_leg",
    "direction_toward",
    "leave_in_min",
    "commute_advice",
    "render_commute",
    "commute_oneline",
]

# Hour-of-day boundary separating the "to work" leg from the "to home" leg.
# Before 14:00 local -> morning (home -> work); 14:00 and later -> evening.
_MORNING_BEFORE_HOUR = 14

# ANSI helpers (rendering only; logic stays plain).
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_ORANGE = "\033[38;5;208m"

# Type aliases for the injectable collaborators (keeps tests clock-free).
LineLoader = Callable[[str], Line]
StationFinder = Callable[[Line, str], Station]
DepartureSource = Callable[
    [Line, Station, datetime, int], tuple[list[Departure], str]
]


@dataclass(frozen=True)
class CommuteAdvice:
    """Immutable result of a commute decision.

    Attributes:
        line: The line the user boards.
        station: The boarding station.
        heading: Human-readable leg label, e.g. ``"Home -> Work"``.
        trains: Upcoming catchable departures (already filtered/sorted).
        leave_in_min: Minutes until the user must leave to catch the soonest
            train in ``trains`` (never negative; ``0`` means leave now).
        source_label: ``"ODPT"`` or ``"STATIC"`` -- provenance of ``trains``.
        dest_station: The leg's destination station (for display).
    """

    line: Line
    station: Station
    heading: str
    trains: list[Departure]
    leave_in_min: int
    source_label: str
    dest_station: Station


def is_morning(now: datetime, *, before_hour: int = _MORNING_BEFORE_HOUR) -> bool:
    """Return ``True`` when ``now`` falls in the morning (home -> work) leg.

    The boundary is ``before_hour`` (default 14:00 local). Anything strictly
    before that hour is morning; ``before_hour:00`` onward is evening. Kept as a
    small pure helper so the threshold can be exercised without a real clock.
    """
    return now.hour < before_hour


def resolve_leg(
    config: object, now: datetime
) -> Optional[tuple[tuple[str, str], tuple[str, str], str]]:
    """Pick the active leg as ``(origin, destination, heading)``.

    ``origin`` / ``destination`` are ``(line_key, station_key)`` pairs taken
    from ``config.home`` / ``config.work``. Returns ``None`` when either
    endpoint is unconfigured. In the morning the user travels home -> work; in
    the evening, work -> home.
    """
    home = getattr(config, "home", None)
    work = getattr(config, "work", None)
    if not _is_pair(home) or not _is_pair(work):
        return None

    if is_morning(now):
        return (home, work, "Home -> Work")
    return (work, home, "Work -> Home")


def _is_pair(value: object) -> bool:
    """Return ``True`` for a 2-element ``(str, str)`` tuple/list."""
    return (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def direction_toward(
    line: Line, origin: Station, dest: Station
) -> Optional[str]:
    """Return the ``Direction.id`` that travels from ``origin`` toward ``dest``.

    For a straight line the direction is chosen by comparing station indices:
    a higher destination index means "forward" (the second direction), a lower
    index means "backward" (the first direction). For a loop line the shorter
    arc around the ring decides the direction. Returns ``None`` when the line
    declares no directions or the stations cannot be located.
    """
    directions = tuple(line.directions or ())
    if not directions:
        return None

    ids = _index_of(line, origin)
    ide = _index_of(line, dest)
    if ids is None or ide is None or ids == ide:
        return None

    count = len(line.stations)
    if line.loop and count > 0:
        forward_arc = (ide - ids) % count
        backward_arc = (ids - ide) % count
        forward = forward_arc <= backward_arc
    else:
        forward = ide > ids

    # First declared direction is treated as "forward" along the station order
    # (index increasing); the second as "backward". Lines with a single
    # direction fall back to that sole direction.
    if forward:
        return directions[0].id
    return directions[-1].id if len(directions) > 1 else directions[0].id


def _index_of(line: Line, station: Station) -> Optional[int]:
    """Return the index of ``station`` on ``line`` by id, else ``None``."""
    for i, candidate in enumerate(line.stations):
        if candidate.id == station.id:
            return i
    return None


def leave_in_min(train_time: str, now: datetime, buffer_min: int) -> int:
    """Minutes until the user must leave to catch a ``"HH:MM"`` departure.

    Computed as ``(train_time - now) - buffer_min`` and clamped at ``0`` (never
    negative). Returns ``None``-equivalent ``-1`` only is avoided: an
    unparseable time yields ``0`` so the caller degrades to "leave now" rather
    than crashing.
    """
    minutes_to_train = _minutes_until(train_time, now)
    if minutes_to_train is None:
        return 0
    remaining = minutes_to_train - max(buffer_min, 0)
    return remaining if remaining > 0 else 0


def _minutes_until(hhmm: str, now: datetime) -> Optional[int]:
    """Whole minutes from ``now`` to the ``"HH:MM"`` time today (no wrap)."""
    parsed = _parse_hhmm(hhmm)
    if parsed is None:
        return None
    hour, minute = parsed
    now_min = now.hour * 60 + now.minute
    train_min = (hour % 24) * 60 + minute
    return train_min - now_min


def _parse_hhmm(value: str) -> Optional[tuple[int, int]]:
    """Parse ``"HH:MM"`` to ``(hour, minute)`` or ``None`` if malformed."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 47 and 0 <= minute <= 59):
        return None
    return hour, minute


def commute_advice(
    config: object,
    now: datetime,
    *,
    limit: int = 4,
    line_loader: LineLoader = load_line,
    station_finder: StationFinder = find_station,
    departure_source: DepartureSource = get_departures,
) -> Optional[CommuteAdvice]:
    """Compute commute advice for ``config`` at ``now``.

    Returns ``None`` when ``home``/``work`` are not both configured, or when the
    leg cannot be resolved (unknown line/station). The collaborators are
    injectable so the decision logic is testable without real data or clocks.
    """
    leg = resolve_leg(config, now)
    if leg is None:
        return None
    origin_ref, dest_ref, heading = leg

    try:
        line = line_loader(origin_ref[0])
        origin = station_finder(line, origin_ref[1])
        dest_line = line_loader(dest_ref[0])
        dest = station_finder(dest_line, dest_ref[1])
    except Exception:
        # Unknown line/station: the guardian simply has nothing to advise.
        return None

    direction = direction_toward(line, origin, dest)
    buffer_min = max(int(getattr(config, "leave_buffer_min", 0) or 0), 0)

    departures, source_label = departure_source(line, origin, now, limit * 3)
    trains = _filter_by_direction(departures, direction)[:limit]

    soonest = trains[0].time if trains else None
    leave = leave_in_min(soonest, now, buffer_min) if soonest else 0

    return CommuteAdvice(
        line=line,
        station=origin,
        heading=heading,
        trains=trains,
        leave_in_min=leave,
        source_label=source_label,
        dest_station=dest,
    )


def _filter_by_direction(
    departures: Sequence[Departure], direction: Optional[str]
) -> list[Departure]:
    """Keep departures matching ``direction``; keep all when unknown/empty.

    Falls back to the unfiltered list if filtering would discard everything, so
    the user is never left with an empty board when the direction id does not
    line up with the source's labelling.
    """
    if not direction:
        return list(departures)
    matched = [d for d in departures if d.direction == direction]
    return matched if matched else list(departures)


# --------------------------------------------------------------------------- #
# Rendering (separate from decision logic; never raises on degraded input).
# --------------------------------------------------------------------------- #


def render_commute(
    advice: Optional[CommuteAdvice], now: datetime, width: int = 60
) -> list[str]:
    """Render the commute board as ANSI text lines (never writes to stdout).

    Layout:
      1. framed header: leg heading + line name (line colour)
      2. the "leave in N min" headline (highlighted)
      3. the next few catchable departures (time + destination)
      4. footer: boarding station -> destination + source label
    """
    iw = _clamp_width(width) - 2

    if advice is None:
        lines = [_frame_top(iw)]
        msg = f"{_DIM}Commute not configured (set [commute] home/work){_RESET}"
        lines.append(_row(_w.safe_pad(msg, iw, "center"), iw))
        lines.append(_frame_top(iw))
        return lines

    line = advice.line
    fg = getattr(line, "ansi_fg", "") or ""
    bg = getattr(line, "ansi_bg", "") or ""

    lines = [_frame_top(iw)]

    badge = f"{bg} {line.symbol} {_RESET}" if bg else f"[{line.symbol}]"
    header = f"  {badge}  {fg}{advice.heading}{_RESET}  {_DIM}{line.name_en}{_RESET}"
    lines.append(_row(header, iw))
    lines.append(_frame_div(iw))

    headline = _leave_headline(advice.leave_in_min, bool(advice.trains))
    lines.append(_row(_w.safe_pad(headline, iw, "center"), iw))
    lines.append(_frame_div(iw))

    if not advice.trains:
        empty = f"{_DIM}No upcoming trains in this direction{_RESET}"
        lines.append(_row(_w.safe_pad(empty, iw, "center"), iw))
    else:
        for dep in advice.trains:
            catch = leave_in_min(dep.time, now, _advice_buffer(advice, now))
            time_cell = f"{_ORANGE}{dep.time}{_RESET}"
            leave_cell = f"{_DIM}leave +{catch}m{_RESET}"
            row = (
                f"  {_w.safe_pad(time_cell, 7)} "
                f"{_w.safe_pad(dep.dest_jp, max(iw - 22, 8))} "
                f"{_w.safe_pad(leave_cell, 10)}"
            )
            lines.append(_row(row, iw))

    lines.append(_frame_div(iw))

    footer_left = f"{_DIM}{advice.station.name_en} -> {advice.dest_station.name_en}{_RESET}"
    footer_right = f"{_DIM}src: {advice.source_label}{_RESET}"
    pad = iw - _w.get_visual_width(footer_left) - _w.get_visual_width(footer_right) - 2
    if pad < 1:
        pad = 1
    footer = f" {footer_left}{' ' * pad}{footer_right} "
    lines.append(_row(footer, iw))
    lines.append(_frame_top(iw))
    return lines


def _leave_headline(leave: int, has_trains: bool) -> str:
    """Build the centred "leave in N min" headline string."""
    if not has_trains:
        return f"{_BOLD}No train to catch{_RESET}"
    if leave <= 0:
        return f"{_BOLD}{_ORANGE}Leave NOW to catch your train{_RESET}"
    return f"{_BOLD}I need to leave in {leave} min{_RESET}"


def _advice_buffer(advice: CommuteAdvice, now: datetime) -> int:
    """Recover the buffer used for ``advice`` from its soonest train.

    ``leave_in_min`` for the soonest train equals ``(t0 - now) - buffer``; we
    invert that to reuse the same buffer for the remaining rows without
    threading config through the renderer.
    """
    if not advice.trains:
        return 0
    minutes_to_first = _minutes_until(advice.trains[0].time, now)
    if minutes_to_first is None:
        return 0
    buffer = minutes_to_first - advice.leave_in_min
    return buffer if buffer > 0 else 0


def commute_oneline(advice: Optional[CommuteAdvice], now: datetime) -> str:
    """Compact one-liner for the statusline (no trailing newline).

    Examples:
        ``[JY] Home->Work · leave in 6m · 08:12 上野・池袋方面``
        ``[JY] Work->Home · leave NOW · 18:03 品川・渋谷方面``
        ``commute: not configured``
    """
    if advice is None:
        return "commute: not configured"

    symbol = getattr(advice.line, "symbol", "") or "??"
    heading = advice.heading.replace(" -> ", "->")

    if not advice.trains:
        return f"[{symbol}] {heading} · no train"

    soonest = advice.trains[0]
    when = "NOW" if advice.leave_in_min <= 0 else f"in {advice.leave_in_min}m"
    dest = soonest.dest_jp.strip()
    tail = f"{soonest.time} {dest}".strip()
    return f"[{symbol}] {heading} · leave {when} · {tail}"
