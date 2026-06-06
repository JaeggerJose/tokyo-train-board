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


from .countdown import departure_display

__all__ = ["statusline_text", "minitable_text"]

# ANSI reset; colours themselves come from the line's own palette at runtime.
_RESET = "\033[0m"

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


def _format_departure(
    dep: Any, now: Any = None, countdown: bool = False
) -> Optional[str]:
    """Format one departure as ``HH:MM 方面`` (or ``あとN分 方面``) or ``None``."""
    raw_time = _safe_attr(dep, "time").strip()
    if not raw_time:
        return None
    time = departure_display(dep, now, countdown) if countdown else raw_time
    dest = _safe_attr(dep, "dest_jp").strip()
    if dest:
        return f"{time} {dest}"
    return time


def _compose_parts(
    line: Any, station: Any, departures: Any, now: Any = None,
    countdown: bool = False,
) -> tuple[str, str, str]:
    """Return ``(badge, label_rest, body)`` as PLAIN text (no colour).

    - ``badge`` is the line code block, e.g. ``[E]`` (gets the line's bg colour).
    - ``label_rest`` is `` 28 都庁前 ▸`` (number, name, arrow; gets the fg colour).
    - ``body`` is the scrollable upcoming-departures list.

    Everything is plain so width maths and marquee slicing stay correct; colour
    is applied afterwards (ANSI is zero-width and would otherwise break slicing).
    """
    badge = _line_badge(line)

    number = _safe_attr(station, "number").strip()
    name = _safe_attr(station, "name_jp").strip() or _safe_attr(station, "name_en").strip()
    if not name:
        name = _safe_attr(station, "id").strip()
    rest = "".join(f" {p}" for p in (number, name) if p) + _STATION_ARROW

    entries: list[str] = []
    if isinstance(departures, Iterable) and not isinstance(departures, (str, bytes)):
        for dep in departures:
            if len(entries) >= _MAX_DEPARTURES:
                break
            formatted = _format_departure(dep, now, countdown)
            if formatted:
                entries.append(formatted)

    if not entries:
        return badge, rest, "--:--"

    # Prefer 2-3 departures; entries already capped at _MAX_DEPARTURES.
    visible = entries[: max(_MIN_DEPARTURES, min(len(entries), _MAX_DEPARTURES))]
    return badge, rest, _DEPARTURE_SEP.join(visible)


def _compose_label_and_body(line: Any, station: Any, departures: Any) -> tuple[str, str]:
    """Return the plain pinned ``label`` and the plain scrollable ``body``."""
    badge, rest, body = _compose_parts(line, station, departures)
    return f"{badge}{rest}", body


def _compose_content(line: Any, station: Any, departures: Any) -> str:
    """Assemble the full (un-scrolled) plain statusline content string."""
    label, body = _compose_label_and_body(line, station, departures)
    return f"{label}{body}"


def _paint(text: str, ansi: str) -> str:
    """Wrap ``text`` in an ANSI sequence + reset, or return it unchanged."""
    return f"{ansi}{text}{_RESET}" if (ansi and text) else text


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
    color: bool = True,
    countdown: bool = False,
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
        color: When ``True`` (default) the badge uses the line's background
            colour and the rest of the line its foreground colour. Set ``False``
            for plain text (e.g. statuslines that strip or dislike ANSI).

    Returns:
        A single line with no trailing newline. Always returns a valid string;
        on internal error it degrades to a minimal label rather than raising.
    """
    try:
        badge, rest, body = _compose_parts(
            line, station, departures, now, countdown
        )
        label = f"{badge}{rest}"          # plain, for width maths + slicing
        content = f"{label}{body}"
    except Exception as exc:  # never let the statusline crash the host shell
        print(f"jrboard.statusline: failed to compose content: {exc!r}",
              file=sys.stderr)
        return "[??] --:--"

    # Line palette (read defensively; absent => no colour applied).
    fg = _safe_attr(line, "ansi_fg") if color else ""
    bg = _safe_attr(line, "ansi_bg") if color else ""

    def paint_label() -> str:
        return f"{_paint(badge, bg)}{_paint(rest, fg)}"

    try:
        # No marquee: whole content fits (or columns disabled).
        if not (columns and columns > 0) or get_visual_width(content) <= columns:
            return f"{paint_label()}{_paint(body, fg)}"

        offset = _seconds_of_day(now)
        if pin_label:
            body_budget = columns - get_visual_width(label)
            # Only pin when the label leaves a usable scrolling window.
            if body_budget >= _MIN_PIN_BODY:
                scrolled = _marquee(body, body_budget, offset)
                return f"{paint_label()}{_paint(scrolled, fg)}"
        # Fallback / pin_label=False: scroll the whole line, paint uniformly.
        return _paint(_marquee(content, columns, offset), fg)
    except Exception as exc:
        print(f"jrboard.statusline: marquee failed: {exc!r}", file=sys.stderr)
        # Best-effort: un-scrolled, still coloured where possible.
        return f"{paint_label()}{_paint(body, fg)}"


# Number of upcoming departures shown in the multi-line minitable body.
_MINITABLE_MIN_ROWS = 2
_MINITABLE_MAX_ROWS = 3


def _minitable_rows(
    departures: Any, now: Any = None, countdown: bool = False
) -> list[tuple[str, str]]:
    """Return up to ``_MINITABLE_MAX_ROWS`` ``(time, dest)`` plain pairs."""
    rows: list[tuple[str, str]] = []
    if isinstance(departures, Iterable) and not isinstance(
        departures, (str, bytes)
    ):
        for dep in departures:
            if len(rows) >= _MINITABLE_MAX_ROWS:
                break
            if not _safe_attr(dep, "time").strip():
                continue
            time = departure_display(dep, now, countdown) if countdown \
                else _safe_attr(dep, "time").strip()
            dest = _safe_attr(dep, "dest_jp").strip()
            rows.append((time, dest))
    return rows


def _fit_line(text: str, columns: int) -> str:
    """Clip a single plain line to ``columns`` visual cols (0 = no clip)."""
    if not (columns and columns > 0):
        return text
    if get_visual_width(text) <= columns:
        return text
    return _slice_to_width(text, 0, columns)


def minitable_text(
    line: Any,
    station: Any,
    departures: Sequence[Any],
    now: Any,
    columns: int = 0,
    color: bool = True,
    token_seg: str = "",
    countdown: bool = False,
) -> str:
    """Render a compact MULTI-LINE statusline table.

    Line 1 is the station identity ``[SYM] <num> <station_jp>`` (line-coloured)
    with ``token_seg`` appended when supplied. The following 2-3 lines list the
    upcoming departures as ``HH:MM  方面`` with line-coloured times.

    Args:
        line: Line value object exposing ``symbol``/``key``/``ansi_fg``/
            ``ansi_bg``.
        station: Station value object exposing ``number``/``name_jp``/
            ``name_en``/``id``.
        departures: Iterable of departure objects exposing ``time`` and
            ``dest_jp``.
        now: Accepted for signature symmetry with :func:`statusline_text`;
            the minitable is not scrolled so it is otherwise unused.
        columns: When ``> 0`` each rendered line is clipped to this many
            visual columns; ``0`` leaves lines untruncated.
        color: When ``True`` the badge takes the line background colour and
            times/labels the line foreground colour.
        token_seg: Optional pre-rendered token gauge appended to line 1.

    Returns:
        A newline-joined string with NO trailing newline. Pure; never raises
        (degrades to a minimal single line on internal error).
    """
    try:
        badge = _line_badge(line)
        number = _safe_attr(station, "number").strip()
        name = (
            _safe_attr(station, "name_jp").strip()
            or _safe_attr(station, "name_en").strip()
            or _safe_attr(station, "id").strip()
        )
        rows = _minitable_rows(departures, now, countdown)
    except Exception as exc:  # never crash the host shell
        print(f"jrboard.statusline: minitable compose failed: {exc!r}",
              file=sys.stderr)
        return "[??] --:--"

    fg = _safe_attr(line, "ansi_fg") if color else ""
    bg = _safe_attr(line, "ansi_bg") if color else ""

    # Line 1: identity, optionally with the token gauge appended. Build the
    # plain string first to decide whether clipping is needed, then colour.
    head_rest = "".join(f" {p}" for p in (number, name) if p)
    suffix = f"  {token_seg}" if token_seg else ""
    head_plain = f"{badge}{head_rest}{suffix}"

    if columns and columns > 0 and get_visual_width(head_plain) > columns:
        # Over budget: emit the clipped plain head (colour would risk slicing
        # an ANSI sequence, so plain text keeps the width exact).
        head = _slice_to_width(head_plain, 0, columns)
    else:
        head = f"{_paint(badge, bg)}{_paint(head_rest, fg)}{suffix}"

    out_lines: list[str] = [head]

    if not rows:
        body_line = _fit_line("--:--", columns)
        out_lines.append(_paint(body_line, fg))
    else:
        visible = rows[: max(_MINITABLE_MIN_ROWS, min(len(rows),
                                                       _MINITABLE_MAX_ROWS))]
        for time, dest in visible:
            plain = f"{time}  {dest}" if dest else time
            plain = _fit_line(plain, columns)
            out_lines.append(_paint(plain, fg))

    return "\n".join(out_lines)


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
