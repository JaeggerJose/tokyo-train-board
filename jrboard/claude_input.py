"""Claude Code statusLine STDIN parsing and selection helpers.

The Claude Code ``statusLine`` command receives a JSON object on STDIN. This
module turns that opaque blob into a small immutable value object
(:class:`ClaudeStatus`) and provides pure, deterministic helpers for:

- deterministic per-session line selection (:func:`pick_by_session`);
- time-bucketed rotation through a pool (:func:`pick_by_rotation`);
- scoping a line pool to a city (:func:`scope_keys_by_city`);
- a compact, colour-graded token-budget gauge (:func:`token_gauge`).

Design constraints:
- Pure: no I/O, no clock reads, no mutation. The caller supplies ``now``.
- Tolerant: a missing or garbage STDIN blob yields an all-``None`` status and
  never raises. Every field of the Claude payload is optional.
- Small and width-aware: statuslines are tight, so :func:`token_gauge` stays
  compact and degrades to ``""`` when nothing is known.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

__all__ = [
    "ClaudeStatus",
    "parse_claude_status",
    "pick_by_session",
    "pick_by_rotation",
    "scope_keys_by_city",
    "token_gauge",
]

# ANSI reset; thresholds drive the green/yellow/red colouring of the gauge.
_RESET = "\033[0m"
_GREEN = "\033[38;5;71m"
_YELLOW = "\033[38;5;179m"
_RED = "\033[38;5;167m"

# Colour-grading thresholds (percent used): <70 green, 70-89 yellow, >=90 red.
_WARN_PCT = 70.0
_CRIT_PCT = 90.0

# Middle dot separating gauge segments; kept short for narrow statuslines.
_SEG_SEP = "·"


@dataclass(frozen=True)
class ClaudeStatus:
    """Immutable view of the fields jrboard reads from the Claude STDIN blob.

    Every field is optional: a missing or unparseable value is ``None`` so
    callers can fall back gracefully without branching on parse errors.
    """

    session_id: Optional[str] = None
    cwd: Optional[str] = None
    model: Optional[str] = None
    ctx_pct: Optional[float] = None
    session_pct: Optional[float] = None
    weekly_pct: Optional[float] = None


def _as_str(value: Any) -> Optional[str]:
    """Return a non-empty string or ``None`` (never raises)."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _as_pct(value: Any) -> Optional[float]:
    """Coerce a 0-100 percentage to ``float``; ``None`` when unusable.

    Bools are rejected (``True``/``False`` are not meaningful percentages) and
    out-of-range numbers are clamped into ``[0, 100]``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            return None
    else:
        return None
    if number != number:  # NaN guard
        return None
    if number < 0.0:
        return 0.0
    if number > 100.0:
        return 100.0
    return number


def _dig(data: Any, *path: str) -> Any:
    """Walk nested mappings by ``path``; ``None`` if any hop is absent."""
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def parse_claude_status(raw: str) -> ClaudeStatus:
    """Tolerantly parse the Claude statusLine STDIN blob.

    Missing, empty, or malformed input yields an all-``None``
    :class:`ClaudeStatus`. Individual fields are coerced defensively and any
    one that is absent or the wrong type simply stays ``None``. Never raises.
    """
    if not isinstance(raw, str) or not raw.strip():
        return ClaudeStatus()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ClaudeStatus()
    if not isinstance(data, dict):
        return ClaudeStatus()

    # cwd lives at .workspace.current_dir, falling back to top-level .cwd.
    cwd = _as_str(_dig(data, "workspace", "current_dir"))
    if cwd is None:
        cwd = _as_str(data.get("cwd"))

    return ClaudeStatus(
        session_id=_as_str(data.get("session_id")),
        cwd=cwd,
        model=_as_str(_dig(data, "model", "display_name")),
        ctx_pct=_as_pct(_dig(data, "context_window", "used_percentage")),
        session_pct=_as_pct(
            _dig(data, "rate_limits", "five_hour", "used_percentage")
        ),
        weekly_pct=_as_pct(
            _dig(data, "rate_limits", "seven_day", "used_percentage")
        ),
    )


def _stable_hash(text: str) -> int:
    """Return a deterministic, process-independent hash of ``text``.

    Python's built-in ``hash`` is salted per process, so we use a SHA-256
    digest to guarantee the same session id maps to the same pool index across
    invocations (the statusline runs as a fresh process every render).
    """
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def pick_by_session(keys: list[str], session_id: str) -> str:
    """Deterministically pick one of ``keys`` from a stable session hash.

    The same ``session_id`` always maps to the same key (so a session keeps a
    stable line), while different sessions distribute across the pool. Raises
    ``ValueError`` when ``keys`` is empty.
    """
    if not keys:
        raise ValueError("pick_by_session: keys must be non-empty")
    if not isinstance(session_id, str) or not session_id:
        # No usable session id: deterministic but arbitrary first choice.
        return keys[0]
    return keys[_stable_hash(session_id) % len(keys)]


def pick_by_rotation(
    keys: list[str], now_epoch: float, period_sec: int
) -> str:
    """Pick one of ``keys`` by a time bucket that advances every period.

    The bucket is ``int(now_epoch) // period_sec``; the chosen key advances
    every ``period_sec`` seconds and wraps over the pool. Raises ``ValueError``
    when ``keys`` is empty. A non-positive ``period_sec`` is treated as ``1``.
    """
    if not keys:
        raise ValueError("pick_by_rotation: keys must be non-empty")
    try:
        epoch = int(now_epoch)
    except (TypeError, ValueError, OverflowError):
        epoch = 0
    period = period_sec if isinstance(period_sec, int) and period_sec > 0 else 1
    bucket = epoch // period
    return keys[bucket % len(keys)]


def scope_keys_by_city(keys: list[str], city: Optional[str]) -> list[str]:
    """Filter ``keys`` to lines whose ``Line.city`` matches ``city``.

    Matching is case-insensitive and whitespace-trimmed. When ``city`` is
    falsy, or nothing matches, the original ``keys`` list is returned unchanged
    (so a typo never empties the pool). A line that fails to load is skipped.
    Never raises.
    """
    if not city or not isinstance(city, str) or not city.strip():
        return keys
    want = city.strip().lower()

    # Imported lazily so this module stays import-safe in isolation/tests.
    try:
        from .model import load_line
    except Exception:
        return keys

    matched: list[str] = []
    for key in keys:
        try:
            if load_line(key).city.strip().lower() == want:
                matched.append(key)
        except Exception:
            continue
    return matched or keys


def _grade_color(pct: float) -> str:
    """Return the ANSI colour for a usage percentage by threshold."""
    if pct >= _CRIT_PCT:
        return _RED
    if pct >= _WARN_PCT:
        return _YELLOW
    return _GREEN


def _segment(label: str, pct: float, color: bool) -> str:
    """Format ``'<label> NN%'``, colour-graded when ``color`` is set."""
    body = f"{label} {int(round(pct))}%"
    if not color:
        return body
    return f"{_grade_color(pct)}{body}{_RESET}"


def token_gauge(
    session_pct: Optional[float],
    weekly_pct: Optional[float],
    ctx_pct: Optional[float] = None,
    color: bool = True,
    max_width: int = 0,
) -> str:
    """Build a compact token-budget gauge for the statusline.

    Renders the known segments joined by a middle dot, e.g.
    ``5h 42% · 7d 18%`` (plus ``ctx 30%`` when given). ``5h`` is the
    SESSION (five-hour) limit and ``7d`` is the WEEKLY (seven-day) limit. Each
    segment is colour-graded: green ``<70``, yellow ``70-89``, red ``>=90``.
    Returns ``""`` when every percentage is ``None``. Never raises.

    Responsive: when ``max_width > 0`` the gauge is shrunk to fit that many
    (plain) columns by dropping the LOWEST-priority segments first — ``ctx``
    goes, then ``7d``, keeping the most important ``5h`` (session) last. Returns
    ``""`` if not even ``5h`` fits. ``max_width <= 0`` means no limit.
    """
    # Highest priority last-to-drop: session (5h) > weekly (7d) > context (ctx).
    candidates: list[tuple[str, float]] = []
    if session_pct is not None:
        candidates.append(("5h", session_pct))
    if weekly_pct is not None:
        candidates.append(("7d", weekly_pct))
    if ctx_pct is not None:
        candidates.append(("ctx", ctx_pct))
    if not candidates:
        return ""

    def _plain_width(selected: list[tuple[str, float]]) -> int:
        # All glyphs here are narrow (ASCII + middle dot), so len == columns.
        return len(_SEG_SEP.join(f"{lbl} {int(round(p))}%" for lbl, p in selected))

    selected = candidates
    if max_width and max_width > 0:
        while selected and _plain_width(selected) > max_width:
            selected = selected[:-1]  # drop the lowest-priority segment
        if not selected:
            return ""
    return _SEG_SEP.join(_segment(lbl, p, color) for lbl, p in selected)
