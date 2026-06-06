"""Tests for the last-train alert + 24h service timeline helpers."""

from __future__ import annotations

import datetime as dt

from jrboard.timeline import (
    is_near_last_train,
    now_fraction,
    render_timeline,
    service_span_min,
    trains_remaining,
)


def _now(h, m):
    return dt.datetime(2026, 6, 6, h, m)


def test_service_span_wraps_past_midnight():
    # 05:11 first -> 00:18 last (next day) ~ 19h 7m
    assert service_span_min("05:11", "00:18") == (24 * 60) - (5 * 60 + 11) + 18


def test_now_fraction_midday_is_between_0_and_1():
    f = now_fraction("05:11", "00:18", _now(15, 0))
    assert f is not None and 0.0 < f < 1.0


def test_now_fraction_before_service_is_none():
    assert now_fraction("05:11", "00:18", _now(3, 0)) is None


def test_now_fraction_after_last_is_none():
    # 00:30 is past the 00:18 last train -> outside service
    assert now_fraction("05:11", "00:18", _now(0, 30)) is None


def test_is_near_last_train_within_window():
    assert is_near_last_train("00:18", _now(23, 41), window_min=90) is True


def test_is_near_last_train_far_is_false():
    assert is_near_last_train("00:18", _now(18, 0), window_min=90) is False


class _Dep:
    def __init__(self, time):
        self.time = time


def test_trains_remaining_counts_through_last():
    deps = [_Dep("23:48"), _Dep("00:00"), _Dep("00:18")]
    # at 23:41, three departures remain up to and including the last train
    assert trains_remaining(deps, "00:18", _now(23, 41)) == 3


def test_render_timeline_contains_first_last_and_now_marker():
    class _Line:
        name_jp = "大江戸線"
        name_en = "Oedo"
        first_train = "05:11"
        last_train = "00:18"

    class _Station:
        name_jp = "六本木"
        name_en = "Roppongi"
        number = "23"

    out = render_timeline(_Line(), _Station(), [_Dep("23:48")], _now(23, 41),
                          width=56)
    text = "\n".join(out)
    assert "05:11" in text and "00:18" in text
    assert "始発" in text and "終電" in text
    assert "now" in text  # the position pointer label
