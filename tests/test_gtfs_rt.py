"""Tests for the GTFS-Realtime overlay source (delays + alerts).

No network and no committed binary fixtures: each test builds a protobuf
``FeedMessage`` in-process and serializes it to the bytes a real feed would
return. The whole module skips cleanly when the optional ``[gtfs]`` extra
(``gtfs-realtime-bindings``) is not installed, so the zero-dep suite stays green.
"""

from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("google.transit.gtfs_realtime_pb2")
from google.transit import gtfs_realtime_pb2 as pb  # noqa: E402

from jrboard.gtfs_rt import GtfsRtSource, decode_feed  # noqa: E402
from jrboard.sources import Departure  # noqa: E402

_ROUTE = "odpt.Railway:JR-East.ChuoRapid"
_NOW = dt.datetime(2026, 6, 7, 12, 0, 0)


def _feed(*, route=_ROUTE, delay_sec=None, alert_text=None,
          alert_routes=None, active_start=None, active_end=None) -> bytes:
    """Build + serialize a GTFS-RT FeedMessage with optional delay/alert."""
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    if delay_sec is not None:
        ent = msg.entity.add()
        ent.id = "tu1"
        ent.trip_update.trip.route_id = route
        stu = ent.trip_update.stop_time_update.add()
        stu.departure.delay = delay_sec
    if alert_text is not None:
        ent = msg.entity.add()
        ent.id = "al1"
        for r in (alert_routes if alert_routes is not None else [route]):
            ie = ent.alert.informed_entity.add()
            ie.route_id = r
        if active_start is not None or active_end is not None:
            ap = ent.alert.active_period.add()
            if active_start is not None:
                ap.start = int(active_start)
            if active_end is not None:
                ap.end = int(active_end)
        tr = ent.alert.header_text.translation.add()
        tr.language = "ja"
        tr.text = alert_text
    return msg.SerializeToString()


def _epoch(h, m=0):
    return dt.datetime(2026, 6, 7, h, m, 0).timestamp()


# --- decode_feed ------------------------------------------------------------

def test_decode_delay_seconds_to_minutes():
    delays, alerts = decode_feed(_feed(delay_sec=120), _NOW)
    assert delays.get(_ROUTE) == 2
    assert alerts == []


def test_decode_extracts_active_ja_alert():
    delays, alerts = decode_feed(_feed(alert_text="人身事故"), _NOW)
    assert any("人身事故" in text for _routes, text in alerts)


def test_decode_drops_alert_outside_active_period():
    raw = _feed(alert_text="強風", active_start=_epoch(20), active_end=_epoch(23))
    _delays, alerts = decode_feed(raw, _NOW)  # now=12:00, window 20:00-23:00
    assert alerts == []


def test_decode_garbage_bytes_is_empty():
    assert decode_feed(b"\xff\xff not protobuf", _NOW) == ({}, [])
    assert decode_feed(b"", _NOW) == ({}, [])


# --- overlay ----------------------------------------------------------------

class _Line:
    def __init__(self, railway):
        self.odpt_railway = railway
        self.key = "chuo_rapid"


def _dep(time, dest="高尾方面", delay=None, alert=None):
    return Departure(time=time, kind_jp="快速", dest_jp=dest, track="2",
                     direction="out", delay_min=delay, alert_text=alert)


def test_overlay_stamps_matching_route(monkeypatch):
    src = GtfsRtSource()
    monkeypatch.setattr(src, "_fetch",
                        lambda url: _feed(delay_sec=180, alert_text="遅延"))
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    deps = [_dep("12:05"), _dep("12:12")]
    out = src.overlay(_Line(_ROUTE), None, _NOW, deps)
    assert all(d.delay_min == 3 for d in out)
    assert all("遅延" in (d.alert_text or "") for d in out)


def test_overlay_non_matching_route_untouched(monkeypatch):
    src = GtfsRtSource()
    monkeypatch.setattr(src, "_fetch", lambda url: _feed(delay_sec=180))
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    out = src.overlay(_Line("odpt.Railway:Other.Line"), None, _NOW, [_dep("12:05")])
    assert out[0].delay_min is None


def test_overlay_is_immutable(monkeypatch):
    src = GtfsRtSource()
    monkeypatch.setattr(src, "_fetch", lambda url: _feed(delay_sec=180))
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    deps = [_dep("12:05")]
    src.overlay(_Line(_ROUTE), None, _NOW, deps)
    assert deps[0].delay_min is None  # original untouched


def test_overlay_preserves_existing_alert_when_feed_silent(monkeypatch):
    src = GtfsRtSource()
    monkeypatch.setattr(src, "_fetch", lambda url: _feed(delay_sec=60))  # no alert
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    deps = [_dep("12:05", alert="既存の運休")]
    out = src.overlay(_Line(_ROUTE), None, _NOW, deps)
    assert out[0].alert_text == "既存の運休"  # kept
    assert out[0].delay_min == 1  # delay still stamped


def test_overlay_route_id_env_override(monkeypatch):
    src = GtfsRtSource()
    monkeypatch.setattr(src, "_fetch", lambda url: _feed(route="R99", delay_sec=120))
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    monkeypatch.setenv("GTFS_RT_ROUTE_ID", "R99")
    out = src.overlay(_Line("unrelated"), None, _NOW, [_dep("12:05")])
    assert out[0].delay_min == 2


# --- chain integration ------------------------------------------------------

def test_get_departures_labels_gtfs_rt_on_stamp(monkeypatch):
    from jrboard import sources
    from jrboard.model import find_station, load_line

    line = load_line("yamanote")
    station = find_station(line, "shinjuku")
    monkeypatch.setenv("GTFS_RT_URL", "http://x")
    monkeypatch.setenv("GTFS_RT_ROUTE_ID", "RY")
    monkeypatch.setattr(sources.GtfsRtSource, "_fetch",
                        lambda self, url: _feed(route="RY", delay_sec=120))
    deps, label = sources.get_departures(line, station, dt.datetime.now(), 3)
    assert label == "GTFS-RT"
    assert any(d.delay_min == 2 for d in deps)


def test_get_departures_falls_back_on_overlay_error(monkeypatch):
    from jrboard import sources
    from jrboard.model import find_station, load_line

    line = load_line("yamanote")
    station = find_station(line, "shinjuku")
    monkeypatch.setenv("GTFS_RT_URL", "http://x")

    def _boom(self, url):
        raise RuntimeError("feed down")

    monkeypatch.setattr(sources.GtfsRtSource, "_fetch", _boom)
    deps, label = sources.get_departures(line, station, dt.datetime.now(), 3)
    assert label in ("STATIC", "ODPT")  # base label, not GTFS-RT
    assert deps  # still returns the base board
