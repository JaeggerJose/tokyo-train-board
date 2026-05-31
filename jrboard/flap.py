"""Split-flap / Solari board animation engine.

This module is PURE: it performs no I/O and has no external dependencies
beyond the standard library, so it is import-safe in isolation.

The engine animates a list of target strings from a fully scrambled state
to their resolved values, mimicking the mechanical character flips of a
Solari split-flap departure board.

Determinism guarantee
----------------------
Every function is deterministic given its ``seed`` argument: all randomness
flows through :class:`random.Random` instances created from explicit seeds.
The same inputs always produce identical output, which keeps frames stable
and testable.

Width / encoding guarantee
--------------------------
:func:`scramble_line` always returns a string with the SAME visual width as
its target and never splits a multibyte character: replacement characters are
drawn from a pool that matches the visual width (1 or 2 cells) of the target
character being scrambled.
"""

from __future__ import annotations

import random
import re
import unicodedata
from typing import Iterator

__all__ = [
    "FLAP_POOL_LATIN",
    "FLAP_POOL_KANA",
    "FLAP_POOL_DIGITS",
    "lock_threshold",
    "scramble_line",
    "flap_frames",
]


# --- Scramble character pools ------------------------------------------------
# Latin and digit pools are width-1 (halfwidth). The kana pool is width-2
# (fullwidth CJK) so it can stand in for wide target characters without
# changing the visual width of a line.
FLAP_POOL_LATIN: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
FLAP_POOL_DIGITS: str = "0123456789"
FLAP_POOL_KANA: str = (
    "アイウエオカキクケコサシスセソタチツテト"
    "ナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
)


# Matches CSI / SGR ANSI escape sequences (e.g. "\033[38;5;148m").
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _char_visual_width(ch: str) -> int:
    """Return the visual cell width (1 or 2) of a single character."""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _pool_for(ch: str) -> str:
    """Pick the scramble pool that preserves ``ch``'s visual width.

    Wide (CJK) characters are replaced from the fullwidth kana pool so the
    line keeps its width. Digits map to the digit pool, everything else
    narrow maps to the Latin pool.
    """
    if _char_visual_width(ch) == 2:
        return FLAP_POOL_KANA
    if ch.isdigit():
        return FLAP_POOL_DIGITS
    return FLAP_POOL_LATIN


def lock_threshold(index: int, total: int, jitter_seed: int) -> float:
    """Progress fraction in ``[0, 1)`` at which position ``index`` locks.

    This is the TUNABLE EASING CURVE of the board. The default models a
    left-to-right wipe: earlier positions lock first, later positions lock
    last, with a small deterministic jitter so the wipe edge looks organic
    rather than a perfectly straight line.

    Design
    ------
    - Base wipe: ``index / total`` maps the leftmost cell to ``0.0`` and the
      rightmost cell toward ``1.0`` (but always strictly below ``1.0`` so the
      final frame can resolve every cell).
    - Jitter: a deterministic per-position offset in roughly
      ``[-0.06, +0.06)`` derived from ``(jitter_seed, index)``. This nudges
      individual cells slightly earlier or later without breaking the overall
      left-to-right feel.
    - The result is clamped to ``[0, 0.999]`` so that a ``progress`` of ``1.0``
      always satisfies ``lock_threshold <= progress`` for every cell.

    To retune the animation, adjust the base curve (e.g. ease-in/ease-out) or
    the jitter amplitude here; nothing else in the module needs to change.

    Parameters
    ----------
    index:
        Zero-based position of the character within the line.
    total:
        Total number of character positions in the line. Values ``<= 0`` are
        treated as ``1`` to avoid division by zero.
    jitter_seed:
        Seed that makes the jitter deterministic per line.
    """
    safe_total = total if total > 0 else 1
    base = index / safe_total

    # Deterministic jitter in [-0.06, +0.06) from a stable hash of the inputs.
    rng = random.Random(f"lock:{jitter_seed}:{index}")
    jitter = (rng.random() - 0.5) * 0.12

    value = base + jitter
    if value < 0.0:
        return 0.0
    if value > 0.999:
        return 0.999
    return value


def _progress_bucket(progress: float) -> int:
    """Quantize ``progress`` into a stable integer bucket.

    Using a bucket (rather than the raw float) for the per-character random
    seed means the scrambled glyph for a still-locking cell stays stable
    within a small progress window and only flips when progress advances a
    meaningful step, which reads as a mechanical flap rather than noise.
    """
    return int(progress * 24)


def scramble_line(target: str, progress: float, seed: int) -> str:
    """Return ``target`` partially scrambled at the given ``progress``.

    The returned string has the SAME visual width as ``target``. For each
    character position:

    - If ``lock_threshold(index, total, seed) <= progress`` the real target
      character is shown.
    - Otherwise a random character is shown, drawn from the pool that matches
      the target character's visual width (so width is preserved and no
      multibyte character is ever split).

    Spaces pass through untouched (they are treated as already locked), and
    ANSI escape sequences (e.g. color codes) are emitted verbatim without
    consuming a character position or affecting visual width.

    Parameters
    ----------
    target:
        The desired final string for this line (may contain ANSI sequences).
    progress:
        Animation progress in ``[0, 1]``. ``>= 1`` resolves every cell.
    seed:
        Deterministic seed for both the lock jitter and the scramble glyphs.
    """
    # Split into ANSI tokens and visible characters, preserving order.
    tokens: list[tuple[bool, str]] = []  # (is_ansi, text)
    pos = 0
    for match in _ANSI_RE.finditer(target):
        if match.start() > pos:
            for ch in target[pos:match.start()]:
                tokens.append((False, ch))
        tokens.append((True, match.group()))
        pos = match.end()
    for ch in target[pos:]:
        tokens.append((False, ch))

    visible_total = sum(1 for is_ansi, _ in tokens if not is_ansi)
    bucket = _progress_bucket(progress)

    out: list[str] = []
    visible_index = 0
    for is_ansi, text in tokens:
        if is_ansi:
            out.append(text)
            continue

        ch = text
        if ch == " " or progress >= 1.0:
            out.append(ch)
            visible_index += 1
            continue

        threshold = lock_threshold(visible_index, visible_total, seed)
        if threshold <= progress:
            out.append(ch)
        else:
            pool = _pool_for(ch)
            char_rng = random.Random(f"scr:{seed}:{visible_index}:{bucket}")
            out.append(pool[char_rng.randrange(len(pool))])
        visible_index += 1

    return "".join(out)


def flap_frames(
    targets: list[str], steps: int = 12, seed: int = 0
) -> Iterator[list[str]]:
    """Yield successive animation frames from full scramble to resolved.

    Each yielded frame is a ``list[str]`` of the same length as ``targets``.
    The first frame is fully (or nearly) scrambled and the LAST frame equals
    ``targets`` exactly. Each line uses a distinct per-line seed derived from
    ``seed`` and its index so lines scramble independently.

    Parameters
    ----------
    targets:
        The final strings the board should resolve to.
    steps:
        Number of frames to emit. Values ``< 1`` are treated as ``1`` and
        yield only the fully resolved frame.
    seed:
        Base seed; combined with each line's index for determinism.
    """
    safe_steps = steps if steps > 0 else 1

    for step in range(safe_steps):
        if safe_steps == 1:
            progress = 1.0
        else:
            progress = step / (safe_steps - 1)

        frame: list[str] = []
        for line_index, target in enumerate(targets):
            # Deterministic per-line seed derived from the base seed and index.
            line_seed = random.Random(f"line:{seed}:{line_index}").randrange(
                2 ** 31
            )
            frame.append(scramble_line(target, progress, line_seed))
        yield frame
