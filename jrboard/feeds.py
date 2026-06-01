"""Local iCalendar (.ics) agenda feed mapped onto ``Departure`` objects.

This lets the board surface "next meetings" the same way it shows trains: an
``.ics`` file is parsed with a tiny hand-written VEVENT scanner (no external
dependencies), and each upcoming event becomes a :class:`Departure` with
``kind_jp='予定'`` (schedule) and ``dest_jp`` set to the event summary.

Parsing is intentionally defensive: a missing file, unreadable file, or
malformed line never raises -- the feed degrades to an empty list. Only events
that start today and at or after ``now`` are returned, sorted ascending and
truncated to ``limit``. The parser handles the common ``DTSTART`` forms:

* ``DTSTART:YYYYMMDDTHHMMSSZ``      (UTC, trailing ``Z``)
* ``DTSTART:YYYYMMDDTHHMMSS``       (floating local time)
* ``DTSTART;TZID=...:YYYYMMDDTHHMMSS`` (parameterised; TZID is ignored,
  the wall-clock value is taken as local)
* ``DTSTART;VALUE=DATE:YYYYMMDD``   (all-day; treated as 00:00 local)

RFC 5545 line folding (continuation lines beginning with a space or tab) is
unfolded before scanning. All times are compared in the naive local wall-clock
domain of ``now`` -- a trailing ``Z`` is stripped but not timezone-converted,
which is sufficient for an offline single-machine agenda board.
"""

from __future__ import annotations

import sys
from datetime import datetime

from jrboard.sources import Departure

__all__ = ["departures_from_ics"]

# Mapping constants for agenda-derived departures.
_AGENDA_KIND_JP = "予定"
_AGENDA_DIRECTION = "agenda"
_AGENDA_TRACK = ""

# Longest summary kept in ``dest_jp`` before truncation (with ellipsis).
_MAX_SUMMARY = 24
_ELLIPSIS = "…"


def _log(message: str) -> None:
    """Emit a namespaced advisory line to stderr (never raises)."""
    print(f"[jrboard] {message}", file=sys.stderr)


def _read_lines(path: str) -> list[str] | None:
    """Return the file's lines, or ``None`` on any read failure (logged)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except FileNotFoundError:
        return None
    except OSError as exc:
        _log(f"could not read ics {path!r}: {exc}")
        return None


def _unfold(lines: list[str]) -> list[str]:
    """Unfold RFC 5545 continuation lines (leading space or tab)."""
    unfolded: list[str] = []
    for raw in lines:
        if raw[:1] in (" ", "\t") and unfolded:
            unfolded[-1] = unfolded[-1] + raw[1:]
        else:
            unfolded.append(raw)
    return unfolded


def _split_property(line: str) -> tuple[str, str] | None:
    """Split an unfolded content line into ``(name_with_params, value)``.

    Returns ``None`` when there is no ``:`` separator (malformed line).
    """
    idx = line.find(":")
    if idx < 0:
        return None
    return line[:idx], line[idx + 1:]


def _property_name(name_with_params: str) -> str:
    """Return the upper-case property name, dropping any ``;`` parameters."""
    return name_with_params.split(";", 1)[0].strip().upper()


def _parse_dtstart(value: str) -> datetime | None:
    """Parse a ``DTSTART`` value into a naive local ``datetime``.

    Handles ``YYYYMMDDTHHMMSS`` (with optional trailing ``Z``) and the
    ``DATE``-only ``YYYYMMDD`` form. Returns ``None`` if unparseable.
    """
    token = value.strip()
    if token.endswith("Z"):
        token = token[:-1]
    if not token:
        return None
    try:
        if "T" in token:
            return datetime.strptime(token, "%Y%m%dT%H%M%S")
        return datetime.strptime(token, "%Y%m%d")
    except ValueError:
        return None


def _truncate_summary(summary: str) -> str:
    """Collapse whitespace and truncate the summary for ``dest_jp``."""
    collapsed = " ".join(summary.split())
    if len(collapsed) <= _MAX_SUMMARY:
        return collapsed
    return collapsed[: _MAX_SUMMARY - 1] + _ELLIPSIS


def _iter_events(lines: list[str]) -> list[tuple[datetime, str]]:
    """Scan unfolded lines into ``(start, summary)`` tuples per VEVENT.

    A lightweight state machine tracks whether we are inside a
    ``BEGIN:VEVENT``/``END:VEVENT`` block, capturing the first ``DTSTART`` and
    ``SUMMARY`` seen. Events lacking a parseable start are skipped.
    """
    events: list[tuple[datetime, str]] = []
    in_event = False
    start: datetime | None = None
    summary = ""

    for line in lines:
        split = _split_property(line)
        if split is None:
            continue
        name_with_params, value = split
        name = _property_name(name_with_params)

        if name == "BEGIN" and value.strip().upper() == "VEVENT":
            in_event = True
            start = None
            summary = ""
            continue
        if name == "END" and value.strip().upper() == "VEVENT":
            if in_event and start is not None:
                events.append((start, summary))
            in_event = False
            start = None
            summary = ""
            continue
        if not in_event:
            continue
        if name == "DTSTART" and start is None:
            start = _parse_dtstart(value)
        elif name == "SUMMARY" and not summary:
            summary = value.strip()

    return events


def departures_from_ics(
    path: str, now: datetime, limit: int = 6
) -> list[Departure]:
    """Map upcoming events from an ``.ics`` file onto :class:`Departure`.

    Keeps only events whose start is on the same calendar date as ``now`` and
    at or after ``now``, sorts ascending by start time, and truncates to
    ``limit``. Returns ``[]`` for a missing/unreadable file, an empty calendar,
    or a non-positive ``limit``. Never raises.
    """
    if limit <= 0:
        return []

    lines = _read_lines(path)
    if not lines:
        return []

    today = now.date()
    upcoming: list[tuple[datetime, str]] = [
        (start, summary)
        for start, summary in _iter_events(_unfold(lines))
        if start.date() == today and start >= now
    ]
    upcoming.sort(key=lambda item: item[0])

    return [
        Departure(
            time=f"{start.hour:02d}:{start.minute:02d}",
            kind_jp=_AGENDA_KIND_JP,
            dest_jp=_truncate_summary(summary),
            track=_AGENDA_TRACK,
            direction=_AGENDA_DIRECTION,
        )
        for start, summary in upcoming[:limit]
    ]
