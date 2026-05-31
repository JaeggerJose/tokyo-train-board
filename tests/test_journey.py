"""Tests for the pomodoro-as-a-train-journey mode (jrboard.journey).

Covers the pure timing logic (progress / remaining_sec) and the renderer's
width invariant (every row is exactly ``width`` visual columns) plus the
arrival end-state. The renderer is exercised with both real Line/Station value
objects and the label-only fallback.
"""

from __future__ import annotations

import time as _time

import pytest

from jrboard.journey import (
    Journey,
    make_journey,
    progress,
    remaining_sec,
    render_journey,
)
from jrboard.model import Line, Station, available_lines, load_line
from jrboard.width import get_visual_width


def _label_station(name: str) -> Station:
    return Station(
        id=name, number="", name_jp=name, kana="", name_en="", odpt_station=""
    )


def _stub_line() -> Line:
    """A minimal Line with no stations to force the label-only fallback."""
    return Line(
        key="test",
        name_jp="テスト線",
        name_en="Test Line",
        symbol="T",
        operator="op",
        odpt_railway="rail",
        loop=False,
        ansi_fg="\033[38;5;148m",
        ansi_bg="\033[48;5;148m\033[38;5;232m",
        hex="#00ff00",
        stations=(),
        first_train="05:00",
        last_train="00:30",
        headway_min={},
        directions=(),
    )


def _real_line() -> Line:
    """Load the first available real line (so station-pair picking is tested)."""
    keys = available_lines()
    assert keys, "expected at least one line JSON for tests"
    return load_line(keys[0])


START = 1_000_000.0
DURATION_MIN = 25
DURATION_SEC = DURATION_MIN * 60


def _journey(line: Line | None = None) -> Journey:
    return make_journey(
        line or _stub_line(),
        _label_station("いま"),
        _label_station("集中"),
        START,
        DURATION_MIN,
    )


# --- progress ---------------------------------------------------------------


def test_progress_zero_at_start() -> None:
    j = _journey()
    assert progress(j, START) == 0.0


def test_progress_zero_before_start() -> None:
    j = _journey()
    assert progress(j, START - 100) == 0.0


def test_progress_one_at_end() -> None:
    j = _journey()
    assert progress(j, START + DURATION_SEC) == 1.0


def test_progress_one_after_end() -> None:
    j = _journey()
    assert progress(j, START + DURATION_SEC + 9999) == 1.0


def test_progress_half_at_midpoint() -> None:
    j = _journey()
    assert progress(j, START + DURATION_SEC / 2) == pytest.approx(0.5)


def test_progress_is_monotonic_non_decreasing() -> None:
    j = _journey()
    prev = -1.0
    for step in range(0, DURATION_SEC + 120, 30):
        cur = progress(j, START + step)
        assert cur >= prev
        assert 0.0 <= cur <= 1.0
        prev = cur


def test_progress_zero_duration_is_complete() -> None:
    j = make_journey(_stub_line(), _label_station("a"), _label_station("b"),
                     START, 0)
    assert progress(j, START) == 1.0


# --- remaining_sec ----------------------------------------------------------


def test_remaining_sec_full_at_start() -> None:
    j = _journey()
    assert remaining_sec(j, START) == DURATION_SEC


def test_remaining_sec_correct_partway() -> None:
    j = _journey()
    assert remaining_sec(j, START + 600) == DURATION_SEC - 600


def test_remaining_sec_zero_at_end() -> None:
    j = _journey()
    assert remaining_sec(j, START + DURATION_SEC) == 0


def test_remaining_sec_zero_after_end() -> None:
    j = _journey()
    assert remaining_sec(j, START + DURATION_SEC + 500) == 0


def test_remaining_sec_never_negative() -> None:
    j = _journey()
    for step in range(0, DURATION_SEC + 300, 45):
        assert remaining_sec(j, START + step) >= 0


# --- make_journey -----------------------------------------------------------


def test_make_journey_uses_given_stations() -> None:
    a, b = _label_station("X"), _label_station("Y")
    j = make_journey(_real_line(), a, b, START, 25)
    assert j.origin is a
    assert j.dest is b
    assert j.duration_sec == 25 * 60


def test_make_journey_picks_pair_from_line_when_none() -> None:
    line = _real_line()
    j = make_journey(line, None, None, START, 25)
    # Both ends must be real stations on the line, and distinct.
    assert j.origin in line.stations
    assert j.dest in line.stations
    assert j.origin.id != j.dest.id


def test_make_journey_longer_session_goes_further() -> None:
    line = _real_line()
    short = make_journey(line, None, None, START, 5)
    long = make_journey(line, None, None, START, 60)
    idx_short = line.stations.index(short.dest)
    idx_long = line.stations.index(long.dest)
    assert idx_long >= idx_short


def test_make_journey_falls_back_to_labels_without_stations() -> None:
    j = make_journey(_stub_line(), None, None, START, 25)
    assert j.origin.name_jp == "いま"
    assert j.dest.name_jp == "集中"


# --- render_journey: width invariant ----------------------------------------


@pytest.mark.parametrize("width", [24, 40, 60, 80, 100])
def test_render_rows_exact_visual_width(width: int) -> None:
    j = _journey(_real_line())
    rows = render_journey(j, START + 600, width=width)
    assert rows, "renderer produced no rows"
    for row in rows:
        assert get_visual_width(row) == width, repr(row)


@pytest.mark.parametrize("width", [40, 60])
def test_render_width_invariant_with_label_fallback(width: int) -> None:
    j = _journey(_stub_line())
    rows = render_journey(j, START + 300, width=width)
    for row in rows:
        assert get_visual_width(row) == width, repr(row)


def test_render_width_invariant_across_progress(width: int = 60) -> None:
    j = _journey(_real_line())
    for step in range(0, DURATION_SEC + 60, 60):
        rows = render_journey(j, START + step, width=width)
        for row in rows:
            assert get_visual_width(row) == width, repr(row)


def test_render_below_min_width_clamps() -> None:
    # A tiny request still produces rows; they must share one consistent width.
    rows = render_journey(_journey(), START, width=5)
    first = get_visual_width(rows[0])
    assert first >= 24
    for row in rows:
        assert get_visual_width(row) == first


# --- render_journey: content -----------------------------------------------


def test_render_header_present() -> None:
    rows = render_journey(_journey(), START, width=60)
    assert any("集中タイマー" in r for r in rows)


def test_render_shows_remaining_minutes_while_running() -> None:
    rows = render_journey(_journey(), START, width=60)
    # 25 min session, nothing elapsed -> "あと 25 分".
    assert any("あと 25 分" in r for r in rows)


def test_render_final_frame_shows_arrival() -> None:
    j = _journey()
    rows = render_journey(j, START + DURATION_SEC, width=60)
    text = "\n".join(rows)
    assert "とうちゃく" in text


def test_render_endpoint_names_present() -> None:
    a, b = _label_station("新宿"), _label_station("東京")
    j = make_journey(_real_line(), a, b, START, 25)
    text = "\n".join(render_journey(j, START + 100, width=70))
    assert "新宿" in text
    assert "東京" in text


def test_render_arrival_clock_present() -> None:
    j = _journey()
    rows = render_journey(j, START, width=60)
    lt = _time.localtime(START + DURATION_SEC)
    clock = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
    assert any(clock in r for r in rows)


def test_render_is_pure_no_exception_on_extreme_now() -> None:
    j = _journey()
    # Far past / far future must not raise and must keep the width invariant.
    for now in (0.0, START - 10_000, START + 10**9):
        rows = render_journey(j, now, width=60)
        for row in rows:
            assert get_visual_width(row) == 60
