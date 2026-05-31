"""Tests for jrboard.width: ANSI stripping and CJK-aware visual width."""

from __future__ import annotations

import pytest

from jrboard.width import get_visual_width, safe_pad, strip_ansi


def test_ascii_width_is_char_count() -> None:
    assert get_visual_width("Shinjuku") == 8


def test_cjk_chars_count_as_two() -> None:
    # Each kanji is a fullwidth glyph occupying two terminal cells.
    assert get_visual_width("新宿") == 4
    assert get_visual_width("山手線") == 6


def test_mixed_cjk_and_ascii() -> None:
    # 2 kanji (4) + space (1) + "Line" (4) = 9
    assert get_visual_width("新宿 Line") == 9


def test_ansi_sequences_have_zero_width() -> None:
    colored = "\033[38;5;148m新宿\033[0m"
    assert get_visual_width(colored) == 4
    assert strip_ansi(colored) == "新宿"


def test_combining_marks_count_zero() -> None:
    # "e" + combining acute accent renders as one cell.
    assert get_visual_width("é") == 1


def test_safe_pad_left_exact_width() -> None:
    padded = safe_pad("AB", 5, "left")
    assert padded == "AB   "
    assert get_visual_width(padded) == 5


def test_safe_pad_right_and_center() -> None:
    assert safe_pad("AB", 5, "right") == "   AB"
    assert safe_pad("AB", 6, "center") == "  AB  "


def test_safe_pad_cjk_target_width_is_visual_not_len() -> None:
    # "新宿" is 4 visual cells; pad to 8 should add exactly 4 spaces.
    padded = safe_pad("新宿", 8, "left")
    assert get_visual_width(padded) == 8
    assert padded == "新宿    "


def test_safe_pad_preserves_ansi_and_pads_visible_width() -> None:
    text = "\033[1m新宿\033[0m"
    padded = safe_pad(text, 8, "left")
    assert get_visual_width(padded) == 8


def test_safe_pad_returns_unchanged_when_already_wider() -> None:
    text = "Shinjuku"
    assert safe_pad(text, 3, "left") == text


def test_safe_pad_rejects_bad_alignment() -> None:
    with pytest.raises(ValueError):
        safe_pad("x", 4, "diagonal")
