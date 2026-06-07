"""Last-train alert + 24h service-timeline helpers.

Answers the late-night question "is it still safe to keep working, or am I about
to miss the last train?" with a compact ASCII service bar (first→last train, a
``now`` pointer) and a remaining-trains count. Pure, stdlib-only; the service
window is allowed to cross midnight (e.g. 05:11 → 00:18 next day).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

__all__ = [
    "service_span_min",
    "now_fraction",
    "is_near_last_train",
    "trains_remaining",
    "render_timeline",
]

_MIN_PER_DAY = 24 * 60


def _hhmm(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 47 and 0 <= minute <= 59):
        return None
    return (hour % 24) * 60 + minute


def _now_min(now: Any) -> Optional[int]:
    hour = getattr(now, "hour", None)
    minute = getattr(now, "minute", None)
    if hour is None or minute is None:
        return None
    try:
        return int(hour) * 60 + int(minute)
    except (TypeError, ValueError):
        return None


def service_span_min(first: Any, last: Any) -> Optional[int]:
    """Total service-window length in minutes; wraps when last < first."""
    f, l = _hhmm(first), _hhmm(last)
    if f is None or l is None:
        return None
    span = l - f
    if span <= 0:
        span += _MIN_PER_DAY
    return span


def _minutes_into_service(first: Any, now: Any) -> Optional[int]:
    f, n = _hhmm(first), _now_min(now)
    if f is None or n is None:
        return None
    pos = n - f
    if pos < 0:
        pos += _MIN_PER_DAY
    return pos


def now_fraction(first: Any, last: Any, now: Any) -> Optional[float]:
    """Position of ``now`` within the service window as 0.0–1.0.

    Returns ``None`` when ``now`` is outside service (before first / after last),
    so a caller can distinguish "running" from "closed".
    """
    span = service_span_min(first, last)
    pos = _minutes_into_service(first, now)
    if span is None or pos is None or span == 0:
        return None
    if pos > span:
        return None  # already past the last train (or before first, wrapped)
    return pos / span


def is_near_last_train(last: Any, now: Any, window_min: int = 90) -> bool:
    """True when ``now`` is within ``window_min`` before (or at) the last train."""
    l, n = _hhmm(last), _now_min(now)
    if l is None or n is None:
        return False
    delta = l - n
    if delta < 0:
        delta += _MIN_PER_DAY
    return 0 <= delta <= window_min


def trains_remaining(departures: Any, last: Any, now: Any) -> int:
    """Count departures from ``now`` up to and including the last train."""
    n = _now_min(now)
    l = _hhmm(last)
    if n is None:
        return 0
    horizon = (l - n) % _MIN_PER_DAY if l is not None else _MIN_PER_DAY
    count = 0
    if isinstance(departures, Iterable) and not isinstance(departures, (str, bytes)):
        for dep in departures:
            t = _hhmm(getattr(dep, "time", None))
            if t is None:
                continue
            if (t - n) % _MIN_PER_DAY <= horizon:
                count += 1
    return count


# --- rendering --------------------------------------------------------------

_WARN = "⚠"


def _attr(obj: Any, name: str, default: str = "") -> str:
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return str(value) if value is not None else default


def render_timeline(
    line: Any, station: Any, departures: Any, now: Any, width: int = 56
) -> list[str]:
    """Render the service timeline as a list of plain text lines.

    Layout::

        大江戸線 ROPPONGI  六本木
        始発 05:11 ┤████████████░░░░░░░░░░┤ 終電 00:18
                                ▲now 23:41
        次の電車: 23:48           ⚠ 終電まで あと2本
        終電:     00:18           ⚠
    """
    first = _attr(line, "first_train")
    last = _attr(line, "last_train")
    name_jp = _attr(line, "name_jp")
    st_jp = _attr(station, "name_jp")
    st_en = _attr(station, "name_en")

    out: list[str] = [f"{name_jp}  {st_en}  {st_jp}".strip()]

    bar_w = max(10, min(width, 60) - 26)  # leave room for the 始発/終電 labels
    frac = now_fraction(first, last, now)
    if frac is None:
        bar = "░" * bar_w
        marker_col = None
    else:
        filled = max(0, min(bar_w, round(frac * bar_w)))
        bar = "█" * filled + "░" * (bar_w - filled)
        marker_col = filled

    out.append(f"始発 {first} ┤{bar}┤ 終電 {last}")

    # Pointer line: place "▲now HH:MM" under the marker column.
    now_hhmm = ""
    nm = _now_min(now)
    if nm is not None:
        now_hhmm = f"{nm // 60:02d}:{nm % 60:02d}"
    if marker_col is not None:
        lead = len("始発 ") + len(first) + len(" ┤") + marker_col
        out.append(" " * lead + f"▲now {now_hhmm}")
    else:
        out.append(f"  (営業時間外 / outside service — now {now_hhmm})")

    near = is_near_last_train(last, now, window_min=90)
    remaining = trains_remaining(departures, last, now)

    nxt = None
    if isinstance(departures, Iterable) and not isinstance(departures, (str, bytes)):
        for dep in departures:
            if _attr(dep, "time"):
                nxt = dep
                break
    if nxt is not None:
        warn = f"   {_WARN} 終電まで あと{remaining}本" if near else ""
        dest = _attr(nxt, "dest_jp")
        out.append(f"次の電車: {_attr(nxt, 'time')}  {dest}{warn}".rstrip())

    last_warn = f"   {_WARN}" if near else ""
    out.append(f"終電:     {last}{last_warn}".rstrip())
    return out
