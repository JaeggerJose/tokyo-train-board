"""Tests for the countdown ("あと N 分") helpers."""

from __future__ import annotations

import datetime as dt

from jrboard.countdown import (
    countdown_minutes,
    departure_display,
    format_countdown,
)


def _now(h, m, s=0):
    return dt.datetime(2026, 6, 6, h, m, s)


def test_countdown_minutes_basic():
    assert countdown_minutes("15:45", _now(15, 42)) == 3


def test_countdown_minutes_floors_partial_minute():
    # 3 min 30 s away -> 3 whole minutes left
    assert countdown_minutes("15:45", _now(15, 41, 30)) == 3


def test_countdown_minutes_imminent_is_zero():
    # 40 s away -> 0 (caller renders "まもなく")
    assert countdown_minutes("15:45", _now(15, 44, 20)) == 0


def test_countdown_minutes_wraps_past_midnight():
    # 00:18 last train seen at 23:41 -> 37 min, not negative
    assert countdown_minutes("00:18", _now(23, 41)) == 37


def test_countdown_minutes_bad_input_is_none():
    assert countdown_minutes("oops", _now(10, 0)) is None
    assert countdown_minutes("15:45", None) is None


def test_format_countdown_labels():
    assert format_countdown(3) == "あと3分"
    assert format_countdown(0) == "まもなく"
    assert format_countdown(None) is None


class _Dep:
    def __init__(self, time):
        self.time = time


def test_departure_display_passthrough_when_off():
    assert departure_display(_Dep("15:45"), _now(15, 42), countdown=False) == "15:45"


def test_departure_display_countdown_when_on():
    assert departure_display(_Dep("15:45"), _now(15, 42), countdown=True) == "あと3分"


def test_departure_display_falls_back_to_time_on_bad_data():
    # countdown requested but time unparseable -> show the raw time string
    assert departure_display(_Dep("??:??"), _now(15, 42), countdown=True) == "??:??"


# --- renderer integration ---------------------------------------------------

class _Line:
    symbol = "JY"
    key = "yamanote"
    name_jp = "山手線"
    name_en = "Yamanote"
    ansi_fg = ""
    ansi_bg = ""


class _Station:
    number = "14"
    name_jp = "新宿"
    name_en = "Shinjuku"
    id = "JY14"
    kana = "しんじゅく"


class _FullDep:
    def __init__(self, time, dest="渋谷方面", kind="普通", track="3"):
        self.time = time
        self.dest_jp = dest
        self.kind_jp = kind
        self.track = track


def test_statusline_countdown_renders_ato_label():
    from jrboard.statusline import statusline_text

    deps = [_FullDep("15:45"), _FullDep("15:50")]
    out = statusline_text(_Line(), _Station(), deps, _now(15, 42),
                          columns=0, color=False, countdown=True)
    assert "あと3分" in out
    assert "15:45" not in out  # absolute time replaced by countdown


def test_statusline_without_countdown_keeps_hhmm():
    from jrboard.statusline import statusline_text

    deps = [_FullDep("15:45")]
    out = statusline_text(_Line(), _Station(), deps, _now(15, 42),
                          columns=0, color=False, countdown=False)
    assert "15:45" in out
    assert "あと" not in out


def test_render_timetable_countdown_widens_and_labels():
    from jrboard.render import render_timetable

    deps = [_FullDep("15:45")]
    lines = render_timetable(_Line(), deps, width=60, countdown=True,
                             now=_now(15, 42))
    assert any("あと3分" in ln for ln in lines)


def test_static_source_orders_by_soonest_across_midnight():
    """Regression: evening departures must not be ranked behind post-midnight
    ones (the absolute mod-24 sort bug that made 'next train' read hours away)."""
    from jrboard.model import find_station, load_line
    from jrboard.sources import StaticSource

    line = load_line("yamanote")
    station = find_station(line, "shinjuku")
    deps = StaticSource().departures(line, station, _now(21, 42), 4)
    assert deps, "expected upcoming departures in the evening"
    # The soonest departure must be minutes away, not 2+ hours.
    assert countdown_minutes(deps[0].time, _now(21, 42)) < 30

