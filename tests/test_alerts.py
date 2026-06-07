"""Tests for the local service-alert overlay and offline cache."""

from __future__ import annotations

import json

from jrboard.alerts import apply_alerts, load_alerts
from jrboard.cache import read_latest, write_snapshot
from jrboard.sources import Departure


def _dep(time, dest="渋谷方面"):
    return Departure(time=time, kind_jp="普通", dest_jp=dest, track="3",
                     direction="outer")


# --- alerts overlay ---------------------------------------------------------

def test_load_alerts_missing_file_is_empty(tmp_path):
    assert load_alerts(str(tmp_path / "nope.json")) == []


def test_load_alerts_reads_list(tmp_path):
    p = tmp_path / "alerts.json"
    p.write_text(json.dumps([{"line": "yamanote", "delay_min": 2}]), encoding="utf-8")
    assert load_alerts(str(p))[0]["delay_min"] == 2


def test_load_alerts_garbage_is_empty(tmp_path):
    p = tmp_path / "alerts.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_alerts(str(p)) == []


def test_apply_alerts_stamps_matching_time():
    deps = [_dep("21:52"), _dep("21:58")]
    alerts = [{"line": "yamanote", "station": "shinjuku",
               "times": ["21:52"], "delay_min": 2, "reason": "人身事故"}]
    out = apply_alerts(deps, alerts, "yamanote", "shinjuku")
    assert out[0].delay_min == 2 and out[0].alert_text == "人身事故"
    assert out[1].delay_min is None  # untouched


def test_apply_alerts_line_scoped_no_match_is_noop():
    deps = [_dep("21:52")]
    alerts = [{"line": "ginza", "delay_min": 5}]
    out = apply_alerts(deps, alerts, "yamanote", "shinjuku")
    assert out[0].delay_min is None


def test_apply_alerts_empty_times_applies_to_all():
    deps = [_dep("21:52"), _dep("21:58")]
    alerts = [{"line": "yamanote", "reason": "強風"}]  # no times => whole line
    out = apply_alerts(deps, alerts, "yamanote", "shinjuku")
    assert all(d.alert_text == "強風" for d in out)


def test_apply_alerts_is_immutable():
    deps = [_dep("21:52")]
    apply_alerts(deps, [{"line": "yamanote", "delay_min": 9}], "yamanote", "shinjuku")
    assert deps[0].delay_min is None  # original untouched


# --- offline cache ----------------------------------------------------------

def test_cache_roundtrip(tmp_path):
    deps = [_dep("21:52"), _dep("21:58")]
    write_snapshot(str(tmp_path), "yamanote", "shinjuku", deps, now_epoch=1000)
    got = read_latest(str(tmp_path), "yamanote", "shinjuku",
                      now_epoch=1300, max_age_sec=1800)
    assert got is not None
    cached, age_min = got
    assert [d.time for d in cached] == ["21:52", "21:58"]
    assert age_min == 5  # 300 s


def test_cache_too_old_returns_none(tmp_path):
    write_snapshot(str(tmp_path), "yamanote", "shinjuku", [_dep("21:52")], now_epoch=0)
    assert read_latest(str(tmp_path), "yamanote", "shinjuku",
                       now_epoch=99999, max_age_sec=1800) is None


def test_cache_missing_returns_none(tmp_path):
    assert read_latest(str(tmp_path), "x", "y", now_epoch=1, max_age_sec=10) is None


def test_cache_keeps_latest_snapshot(tmp_path):
    write_snapshot(str(tmp_path), "l", "s", [_dep("10:00")], now_epoch=10)
    write_snapshot(str(tmp_path), "l", "s", [_dep("11:00")], now_epoch=20)
    cached, _ = read_latest(str(tmp_path), "l", "s", now_epoch=25, max_age_sec=100)
    assert [d.time for d in cached] == ["11:00"]  # most recent line wins


# --- render integration of the overlay --------------------------------------

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


def test_render_timetable_shows_delay_badge_and_cause():
    from jrboard.render import render_timetable

    deps = [Departure("21:52", "普通", "渋谷方面", "3", "outer",
                      delay_min=2, alert_text="人身事故")]
    text = "\n".join(render_timetable(_Line(), deps, width=60))
    assert "[+2分]" in text
    assert "人身事故" in text  # cause footer


def test_statusline_shows_overlay_badge():
    from jrboard.statusline import statusline_text

    deps = [Departure("21:52", "普通", "渋谷方面", "3", "outer",
                      delay_min=3, alert_text="遅延")]
    out = statusline_text(_Line(), _Station(), deps, None, columns=0, color=False)
    assert "[+3分]" in out and "⚠" in out
