"""Single-line marquee renderer for the Claude Code statusLine.

Produces ONE compact line (no trailing newline) summarizing the next few
departures from a station on a given line. When the rendered content is wider
than the available column budget, the text is scrolled horizontally; the scroll
offset is derived from ``now`` so that successive invocations advance the
marquee.

Design constraints:
- Pure-ish: only depends on :mod:`jrboard.width` for correct CJK measurement.
- Minimal/optional ANSI so the output is safe to embed in a shell statusline.
- No mutation; value objects are read, never modified.
- Comprehensive error handling: a malformed input must never crash the
  statusline (a degraded but valid single line is always returned).
"""

from __future__ import annotations

import datetime as _dt
import sys
from typing import Any, Iterable, Optional, Sequence

try:  # Import-safe: degrade gracefully if width module is unavailable.
    from .width import get_visual_width
except Exception:  # pragma: no cover - fallback only used in isolation.

    def get_visual_width(text: str) -> int:
        """Fallback width: approximate by stripping ANSI and counting chars.

        This is intentionally simple and only used when :mod:`jrboard.width`
        cannot be imported (e.g. when this module is exercised in isolation).
        """
        import re
        import unicodedata

        stripped = re.sub(r"\033\[[0-9;]*m", "", text)
        total = 0
        for ch in stripped:
            total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return total


__all__ = ["statusline_text"]

# Separator placed between consecutive departure entries.
_DEPARTURE_SEP = "  "
# Marquee gap appended when wrapping the scroll so the loop reads cleanly.
_MARQUEE_GAP = "   ·   "  # spaces around a middle dot
# Glyph separating the station label from the departures list.
_STATION_ARROW = " ▸ "  # " ▸ "
# Number of upcoming departures to surface in the compact line.
_MAX_DEPARTURES = 3
_MIN_DEPARTURES = 2


def _seconds_of_day(now: Any) -> int:
    """Return seconds-since-midnight from ``now`` defensively.

    Accepts a :class:`datetime.datetime`/:class:`datetime.time`, anything that
    exposes ``hour``/``minute``/``second`` attributes, or a numeric epoch/second
    value. Falls back to ``0`` when nothing usable is found.
    """
    if now is None:
        return 0
    # datetime / time-like objects.
    hour = getattr(now, "hour", None)
    minute = getattr(now, "minute", None)
    second = getattr(now, "second", None)
    if hour is not None and minute is not None:
        try:
            return int(hour) * 3600 + int(minute) * 60 + int(second or 0)
        except (TypeError, ValueError):
            pass
    # Numeric (epoch seconds or arbitrary tick counter).
    if isinstance(now, (int, float)):
        try:
            return int(now)
        except (TypeError, ValueError, OverflowError):
            return 0
    return 0


def _safe_attr(obj: Any, name: str, default: str = "") -> str:
    """Read a string attribute defensively, coercing to ``str``."""
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _line_badge(line: Any) -> str:
    """Build the compact line badge, e.g. ``[JY]`` from the line symbol."""
    symbol = _safe_attr(line, "symbol").strip()
    if not symbol:
        symbol = _safe_attr(line, "key").strip().upper()[:3]
    if not symbol:
        symbol = "??"
    return f"[{symbol}]"


def _station_label(line: Any, station: Any) -> str:
    """Build the badge + station name segment, e.g. ``[JY] 新宿``."""
    badge = _line_badge(line)
    number = _safe_attr(station, "number").strip()
    name = _safe_attr(station, "name_jp").strip()
    if not name:
        name = _safe_attr(station, "name_en").strip()
    if not name:
        name = _safe_attr(station, "id").strip()
    parts = [badge]
    if number:
        parts.append(number)
    if name:
        parts.append(name)
    return " ".join(p for p in parts if p)


def _format_departure(dep: Any) -> Optional[str]:
    """Format one departure as ``HH:MM 方面`` or ``None`` when unusable."""
    time = _safe_attr(dep, "time").strip()
    if not time:
        return None
    dest = _safe_attr(dep, "dest_jp").strip()
    if dest:
        return f"{time} {dest}"
    return time


def _compose_label_and_body(line: Any, station: Any, departures: Any) -> tuple[str, str]:
    """Return the pinned ``label`` segment and the scrollable ``body``.

    ``label`` is the station identity (e.g. ``[E] 28 都庁前 ▸``) that should
    stay visible; ``body`` is the upcoming-departures list that may be scrolled
    as a marquee when the column budget is tight.
    """
    label = f"{_station_label(line, station)}{_STATION_ARROW}"

    entries: list[str] = []
    if isinstance(departures, Iterable) and not isinstance(departures, (str, bytes)):
        for dep in departures:
            if len(entries) >= _MAX_DEPARTURES:
                break
            formatted = _format_departure(dep)
            if formatted:
                entries.append(formatted)

    if not entries:
        return label, "--:--"

    # Prefer 2-3 departures; entries already capped at _MAX_DEPARTURES.
    visible = entries[: max(_MIN_DEPARTURES, min(len(entries), _MAX_DEPARTURES))]
    return label, _DEPARTURE_SEP.join(visible)


def _compose_content(line: Any, station: Any, departures: Any) -> str:
    """Assemble the full (un-scrolled) statusline content string."""
    label, body = _compose_label_and_body(line, station, departures)
    return f"{label}{body}"


def _slice_to_width(text: str, start_col: int, target_w: int) -> str:
    """Return a substring of ``text`` spanning visual columns.

    Walks characters accumulating visual width, beginning at visual column
    ``start_col`` and yielding up to ``target_w`` columns. CJK-wide characters
    are treated atomically: if a 2-wide glyph would straddle a boundary it is
    dropped and a single space is emitted to preserve exact alignment.
    """
    if target_w <= 0:
        return ""

    out: list[str] = []
    col = 0  # current visual column as we scan from the left
    emitted = 0  # visual columns emitted into the output window

    for ch in text:
        ch_w = get_visual_width(ch)
        # Skip characters entirely left of the window.
        if col + ch_w <= start_col:
            col += ch_w
            continue
        # A wide char straddling the left edge: emit a pad space for the
        # visible half so columns line up.
        if col < start_col < col + ch_w:
            if emitted < target_w:
                out.append(" ")
                emitted += 1
            col += ch_w
            continue
        # Char fully inside (or at) the window start.
        if emitted + ch_w > target_w:
            # Wide char would overflow the right edge: pad the remaining slot.
            while emitted < target_w:
                out.append(" ")
                emitted += 1
            break
        out.append(ch)
        emitted += ch_w
        col += ch_w
        if emitted >= target_w:
            break

    # Right-pad if the source ran out before filling the window.
    while emitted < target_w:
        out.append(" ")
        emitted += 1
    return "".join(out)


def _marquee(content: str, columns: int, offset_seconds: int) -> str:
    """Scroll ``content`` to fit ``columns``, advancing by ``offset_seconds``.

    The scrolling track is ``content`` followed by a gap, repeated, so the
    marquee wraps seamlessly. The horizontal offset advances one visual column
    per second derived from ``now``.
    """
    track = content + _MARQUEE_GAP
    track_w = get_visual_width(track)
    if track_w <= 0:
        return _slice_to_width(content, 0, columns)

    start = offset_seconds % track_w
    # Build a doubled track so a window starting late still has content to show.
    doubled = track + track
    return _slice_to_width(doubled, start, columns)


# Minimum columns of scrolling room before pinning is worthwhile; below this
# the pinned label leaves too little space and we fall back to scrolling all.
_MIN_PIN_BODY = 8


def statusline_text(
    line: Any,
    station: Any,
    departures: Sequence[Any],
    now: Any,
    columns: int = 0,
    pin_label: bool = True,
) -> str:
    """Render the one-line statusline string.

    Args:
        line: A line value object exposing ``symbol``/``key`` (and ideally
            ``name_jp``).
        station: A station value object exposing ``number``/``name_jp``/
            ``name_en``/``id``.
        departures: Iterable of departure value objects exposing ``time``
            (``"HH:MM"``) and ``dest_jp``.
        now: Current time, used to derive the marquee scroll offset. Accepts a
            :class:`datetime.datetime`, :class:`datetime.time`, or a numeric
            second/epoch counter.
        columns: Available terminal width. When ``<= 0`` no marquee is applied
            and the full content is returned untruncated.
        pin_label: When ``True`` (default) the station-identity segment
            (``[E] 28 都庁前 ▸``) stays fixed and only the departures list
            scrolls as a marquee. When ``False`` the entire line scrolls.

    Returns:
        A single line with no trailing newline. Always returns a valid string;
        on internal error it degrades to a minimal label rather than raising.
    """
    try:
        label, body = _compose_label_and_body(line, station, departures)
        content = f"{label}{body}"
    except Exception as exc:  # never let the statusline crash the host shell
        print(f"jrboard.statusline: failed to compose content: {exc!r}",
              file=sys.stderr)
        return "[??] --:--"

    try:
        if not (columns and columns > 0):
            return content
        if get_visual_width(content) <= columns:
            return content

        offset = _seconds_of_day(now)
        if pin_label:
            label_w = get_visual_width(label)
            body_budget = columns - label_w
            # Only pin when the label leaves a usable scrolling window.
            if body_budget >= _MIN_PIN_BODY:
                return label + _marquee(body, body_budget, offset)
        # Fallback / pin_label=False: scroll the whole line.
        return _marquee(content, columns, offset)
    except Exception as exc:
        print(f"jrboard.statusline: marquee failed: {exc!r}", file=sys.stderr)
        # Best-effort: return the un-scrolled content so the user still sees data.
        return content


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    # Lightweight self-check using simple stand-in objects so the module can be
    # exercised in isolation without the rest of the package present.
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _L:
        symbol: str
        key: str
        name_jp: str

    @dataclass(frozen=True)
    class _S:
        number: str
        name_jp: str
        name_en: str
        id: str

    @dataclass(frozen=True)
    class _D:
        time: str
        dest_jp: str

    _line = _L(symbol="JY", key="yamanote", name_jp="山手線")
    _station = _S(number="14", name_jp="新宿", name_en="Shinjuku", id="JY14")
    _deps = [
        _D(time="08:01", dest_jp="品川・渋谷方面"),
        _D(time="08:04", dest_jp="上野・池袋方面"),
        _D(time="08:07", dest_jp="品川・渋谷方面"),
    ]
    full = statusline_text(_line, _station, _deps, _dt.datetime(2026, 5, 31, 8, 0, 0))
    print(full)
    print(f"width={get_visual_width(full)}")
    for sec in range(0, 6):
        scrolled = statusline_text(
            _line, _station, _deps,
            _dt.datetime(2026, 5, 31, 8, 0, sec), columns=30,
        )
        print(f"{sec}: |{scrolled}| w={get_visual_width(scrolled)}")
