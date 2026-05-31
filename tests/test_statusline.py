"""Tests for the single-line statusline marquee renderer."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from jrboard.statusline import statusline_text
from jrboard.width import get_visual_width


@dataclass(frozen=True)
class _Line:
    symbol: str
    key: str
    name_jp: str


@dataclass(frozen=True)
class _Station:
    number: str
    name_jp: str
    name_en: str
    id: str


@dataclass(frozen=True)
class _Dep:
    time: str
    dest_jp: str


LINE = _Line(symbol="E", key="oedo", name_jp="大江戸線")
STATION = _Station(number="28", name_jp="都庁前", name_en="Tochomae", id="E28")
DEPS = [
    _Dep("15:18", "六本木方面"),
    _Dep("15:18", "両国方面"),
    _Dep("15:24", "六本木方面"),
]
NOW = dt.datetime(2026, 5, 31, 15, 0, 0)


def test_full_content_unscrolled_when_columns_zero() -> None:
    text = statusline_text(LINE, STATION, DEPS, NOW, columns=0)
    assert "都庁前" in text
    assert "六本木方面" in text


def test_no_marquee_when_content_fits() -> None:
    text = statusline_text(LINE, STATION, DEPS, NOW, columns=0)
    wide = get_visual_width(text) + 10
    assert statusline_text(LINE, STATION, DEPS, NOW, columns=wide) == text


def test_pin_label_keeps_station_visible() -> None:
    # Narrow window forces a marquee; the station identity must stay pinned.
    for sec in range(0, 12):
        now = dt.datetime(2026, 5, 31, 15, 0, sec)
        text = statusline_text(LINE, STATION, DEPS, now, columns=40, pin_label=True)
        assert text.startswith("[E] 28 都庁前 ▸"), text
        assert get_visual_width(text) <= 40


def test_scroll_all_may_drop_label() -> None:
    # In full-scroll mode the label is not guaranteed pinned; just stay in budget.
    text = statusline_text(LINE, STATION, DEPS, NOW, columns=40, pin_label=False)
    assert get_visual_width(text) <= 40


def test_marquee_advances_with_time() -> None:
    a = statusline_text(LINE, STATION, DEPS, dt.datetime(2026, 5, 31, 15, 0, 0),
                        columns=40)
    b = statusline_text(LINE, STATION, DEPS, dt.datetime(2026, 5, 31, 15, 0, 5),
                        columns=40)
    assert a != b


def test_no_departures_degrades_gracefully() -> None:
    text = statusline_text(LINE, STATION, [], NOW, columns=0)
    assert "都庁前" in text
    assert "--:--" in text


@dataclass(frozen=True)
class _ColorLine:
    symbol: str
    key: str
    name_jp: str
    ansi_fg: str
    ansi_bg: str


COLOR_LINE = _ColorLine(
    symbol="JY", key="yamanote", name_jp="山手線",
    ansi_fg="\033[38;5;148m", ansi_bg="\033[48;5;148m\033[38;5;232m",
)


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def test_color_wraps_badge_and_body() -> None:
    text = statusline_text(COLOR_LINE, STATION, DEPS, NOW, columns=0, color=True)
    assert "\033[48;5;148m" in text  # badge background colour present
    assert "\033[38;5;148m" in text  # foreground colour present
    # Stripping ANSI must recover the plain content unchanged.
    assert "都庁前" in _strip_ansi(text)


def test_color_false_is_plain() -> None:
    text = statusline_text(COLOR_LINE, STATION, DEPS, NOW, columns=0, color=False)
    assert "\033[" not in text


def test_color_does_not_change_visual_width_budget() -> None:
    # Colour codes are zero-width: a coloured marquee still respects columns.
    text = statusline_text(COLOR_LINE, STATION, DEPS, NOW, columns=40, color=True)
    assert get_visual_width(text) <= 40


def test_never_raises_on_garbage_input() -> None:
    # Defensive: malformed objects must not crash the host shell.
    text = statusline_text(object(), object(), None, NOW, columns=20)
    assert isinstance(text, str)
    assert text  # non-empty
