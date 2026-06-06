"""Countdown ("あと N 分") helpers.

Turn an ``"HH:MM"`` departure time into a live, decrementing label so the board
visibly changes on every render (this is what makes the Claude statusLine feel
alive instead of frozen between renders). Pure and stdlib-only; shared by the
board, statusline and minitable renderers so the time->countdown logic lives in
exactly one place.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = ["countdown_minutes", "format_countdown", "departure_display"]

_SEC_PER_DAY = 24 * 60 * 60


def _seconds_of_day(now: Any) -> Optional[int]:
    """Seconds since midnight from a datetime/time-like object, else ``None``."""
    hour = getattr(now, "hour", None)
    minute = getattr(now, "minute", None)
    second = getattr(now, "second", None)
    if hour is None or minute is None:
        return None
    try:
        return int(hour) * 3600 + int(minute) * 60 + int(second or 0)
    except (TypeError, ValueError):
        return None


def _hhmm_to_seconds(value: str) -> Optional[int]:
    """Seconds since midnight for ``"HH:MM"`` (hours mod 24), else ``None``."""
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
    return ((hour % 24) * 60 + minute) * 60


def countdown_minutes(dep_time: Any, now: Any) -> Optional[int]:
    """Whole minutes (floored) until ``dep_time`` from ``now``; ``None`` if bad.

    Wrap-aware: a departure whose ``HH:MM`` already passed today is treated as
    being tomorrow (matching the board, which only ever shows future trains), so
    e.g. the 00:18 last train seen at 23:41 reads 37 — never a negative number.
    """
    dep_sec = _hhmm_to_seconds(dep_time)
    now_sec = _seconds_of_day(now)
    if dep_sec is None or now_sec is None:
        return None
    delta = dep_sec - now_sec
    if delta < 0:
        delta += _SEC_PER_DAY
    return delta // 60


def format_countdown(minutes: Optional[int]) -> Optional[str]:
    """Render minutes as ``"あと3分"``; ``"まもなく"`` at 0; ``None`` passes through."""
    if minutes is None:
        return None
    if minutes <= 0:
        return "まもなく"
    return f"あと{minutes}分"


def departure_display(dep: Any, now: Any, countdown: bool = False) -> str:
    """Time string to show for ``dep``: the countdown label or the raw ``HH:MM``.

    Falls back to the raw time string when countdown is off or uncomputable, so
    a renderer can call this unconditionally.
    """
    time = ""
    try:
        time = (getattr(dep, "time", "") or "").strip()
    except Exception:
        time = ""
    if not countdown:
        return time
    label = format_countdown(countdown_minutes(time, now))
    return label if label is not None else time
