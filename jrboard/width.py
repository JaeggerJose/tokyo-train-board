"""Visual width helpers for terminal rendering.

Handles ANSI escape stripping and CJK (East Asian wide) character widths so
that text padding lines up correctly in a fixed-width terminal board.
"""

from __future__ import annotations

import re
import unicodedata

# Matches ANSI CSI escape sequences such as "\033[38;5;148m" or "\033[0m".
_ANSI_RE = re.compile(r"\033\[[0-9;?]*[ -/]*[@-~]")

# East Asian width classes that occupy two terminal cells.
_WIDE_CLASSES = frozenset({"W", "F"})

_ALIGNMENTS = frozenset({"left", "right", "center"})


def strip_ansi(text: str) -> str:
    """Return ``text`` with all ANSI escape sequences removed."""
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    return _ANSI_RE.sub("", text)


def get_visual_width(text: str) -> int:
    """Return the visible terminal column width of ``text``.

    ANSI escape sequences are stripped first (they occupy no columns). Each
    East Asian wide/fullwidth character counts as 2 columns; everything else
    counts as 1. Zero-width combining marks count as 0.
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")

    visible = strip_ansi(text)
    width = 0
    for ch in visible:
        if unicodedata.combining(ch):
            continue
        if unicodedata.east_asian_width(ch) in _WIDE_CLASSES:
            width += 2
        else:
            width += 1
    return width


def safe_pad(text: str, target_w: int, align: str = "left") -> str:
    """Pad ``text`` with spaces to an exact visual width of ``target_w``.

    ``align`` is one of ``{"left", "right", "center"}``. If ``text`` is already
    wider than ``target_w`` it is returned unchanged. ANSI sequences embedded in
    ``text`` are preserved and ignored when measuring width.
    """
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    if not isinstance(target_w, int):
        raise TypeError(f"target_w must be int, got {type(target_w).__name__}")
    if align not in _ALIGNMENTS:
        raise ValueError(
            f"align must be one of {sorted(_ALIGNMENTS)}, got {align!r}"
        )

    current = get_visual_width(text)
    if current >= target_w:
        return text

    pad = target_w - current
    if align == "left":
        return text + " " * pad
    if align == "right":
        return " " * pad + text
    left = pad // 2
    right = pad - left
    return " " * left + text + " " * right
