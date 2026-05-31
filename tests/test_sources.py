"""Tests for jrboard.sources: static generation and ODPT fallback."""

from __future__ import annotations

from datetime import datetime

import pytest

from jrboard.model import load_line
from jrboard.sources import (
    Departure,
    StaticSource,
    get_departures,
)


@pytest.fixture()
def yamanote():
    line = load_line("yamanote")
    station = line.stations[16]  # Shinjuku
    return line, station


def _to_minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return (int(hour) % 24) * 60 + int(minute)


def test_static_departures_are_future_only(yamanote) -> None:
    line, station = yamanote
    now = datetime(2026, 5, 31, 8, 0, 0)  # 08:00
    deps = StaticSource().departures(line, station, now, limit=6)
    assert deps
    now_min = now.hour * 60 + now.minute
    for dep in deps:
        assert _to_minutes(dep.time) >= now_min


def test_static_departures_are_sorted_by_time(yamanote) -> None:
    line, station = yamanote
    now = datetime(2026, 5, 31, 8, 0, 0)
    deps = StaticSource().departures(line, station, now, limit=6)
    times = [_to_minutes(d.time) for d in deps]
    assert times == sorted(times)


def test_static_departures_respect_limit(yamanote) -> None:
    line, station = yamanote
    now = datetime(2026, 5, 31, 8, 0, 0)
    deps = StaticSource().departures(line, station, now, limit=4)
    assert len(deps) == 4
    assert all(isinstance(d, Departure) for d in deps)


def test_static_departures_cover_both_directions(yamanote) -> None:
    line, station = yamanote
    now = datetime(2026, 5, 31, 8, 0, 0)
    deps = StaticSource().departures(line, station, now, limit=6)
    direction_ids = {d.direction for d in deps}
    # Yamanote has inner + outer; both should appear in a healthy window.
    assert direction_ids == {"inner", "outer"}


def test_static_limit_zero_returns_empty(yamanote) -> None:
    line, station = yamanote
    now = datetime(2026, 5, 31, 8, 0, 0)
    assert StaticSource().departures(line, station, now, limit=0) == []


def test_get_departures_falls_back_to_static_without_key(
    yamanote, monkeypatch
) -> None:
    line, station = yamanote
    monkeypatch.delenv("ODPT_KEY", raising=False)
    now = datetime(2026, 5, 31, 8, 0, 0)
    deps, label = get_departures(line, station, now, limit=6)
    assert label == "STATIC"
    assert deps
    assert len(deps) <= 6


def test_get_departures_falls_back_when_odpt_errors(
    yamanote, monkeypatch, capsys
) -> None:
    """A failing ODPT source must log to stderr and degrade to STATIC."""
    line, station = yamanote
    monkeypatch.setenv("ODPT_KEY", "dummy-key")

    import jrboard.sources as sources_mod

    class _Boom:
        def departures(self, *_args, **_kwargs):
            raise RuntimeError("simulated ODPT outage")

    monkeypatch.setattr(sources_mod, "ODPTSource", _Boom)

    now = datetime(2026, 5, 31, 8, 0, 0)
    deps, label = get_departures(line, station, now, limit=6)
    assert label == "STATIC"
    assert deps
    err = capsys.readouterr().err
    assert "ODPT source failed" in err
