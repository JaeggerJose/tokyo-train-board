"""Toei timetables come from ODPT's keyless public endpoint (opt-in).

Covers the station ids (a wrong-cased id makes ODPT return nothing and the
board silently falls back to estimates), the endpoint choice, the per-day
cache with its failure cooldown, post-midnight ordering, and the opt-in
switch in ``get_departures``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from jrboard import odpt_fetch, sources
from jrboard.model import find_station, load_line

_FIXTURE = Path(__file__).parent / "fixtures" / "odpt_toei_subway_stations.json"
_TOEI_LINES = {
    "asakusa": "Asakusa", "mita": "Mita", "shinjuku": "Shinjuku", "oedo": "Oedo",
}


# --- station ids ------------------------------------------------------------ #

@pytest.mark.parametrize("key, railway", sorted(_TOEI_LINES.items()))
def test_toei_ids_match_the_official_odpt_list(key: str, railway: str) -> None:
    official = set(json.loads(_FIXTURE.read_text(encoding="utf-8"))["ids"])
    line = load_line(key)
    assert line.odpt_railway == f"odpt.Railway:Toei.{railway}"
    unknown = [s.odpt_station for s in line.stations if s.odpt_station not in official]
    assert not unknown, f"{key}: ids ODPT does not know: {unknown}"


# --- endpoint --------------------------------------------------------------- #

def test_toei_uses_the_public_endpoint_without_a_key() -> None:
    url, auth = odpt_fetch.endpoint_for("odpt.Station:Toei.Shinjuku.Shinjuku", None)
    assert url == odpt_fetch.PUBLIC_TIMETABLE_URL
    assert auth == {}


def test_other_operators_need_a_key() -> None:
    station = "odpt.Station:TokyoMetro.Ginza.Shibuya"
    with pytest.raises(RuntimeError, match="ODPT_KEY"):
        odpt_fetch.endpoint_for(station, None)
    url, auth = odpt_fetch.endpoint_for(station, "k")
    assert url == odpt_fetch.KEYED_TIMETABLE_URL
    assert auth == {"acl:consumerKey": "k"}


# --- cache and cooldown ----------------------------------------------------- #

_PARAMS = {"odpt:station": "odpt.Station:Toei.Shinjuku.Shinjuku"}
_PAYLOAD = [{"odpt:stationTimetableObject": [{"odpt:departureTime": "05:00"}]}]


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fake HTTP layer that records each requested URL."""
    calls: list[str] = []

    def fake_get_json(url: str) -> object:
        calls.append(url)
        return _PAYLOAD

    monkeypatch.setattr(odpt_fetch, "_http_get_json", fake_get_json)
    return calls


def test_a_station_is_fetched_once_per_day(http: list[str], tmp_path: Path) -> None:
    for _ in range(3):
        assert odpt_fetch.fetch_timetable(_PARAMS, None, cache_root=tmp_path) == _PAYLOAD
    assert len(http) == 1


def test_a_stale_cache_is_refetched(http: list[str], tmp_path: Path) -> None:
    odpt_fetch.fetch_timetable(_PARAMS, None, cache_root=tmp_path)
    day_old = os.path.getmtime(next(tmp_path.glob("*.json"))) - odpt_fetch.CACHE_TTL_S - 1
    for path in tmp_path.glob("*.json"):
        os.utime(path, (day_old, day_old))
    odpt_fetch.fetch_timetable(_PARAMS, None, cache_root=tmp_path)
    assert len(http) == 2


def test_a_failure_is_not_retried_during_the_cooldown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def offline(url: str) -> object:
        calls.append(url)
        raise OSError("network is unreachable")

    monkeypatch.setattr(odpt_fetch, "_http_get_json", offline)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            odpt_fetch.fetch_timetable(_PARAMS, None, cache_root=tmp_path)
    assert len(calls) == 1


def test_the_key_never_reaches_the_disk(http: list[str], tmp_path: Path) -> None:
    params = {"odpt:station": "odpt.Station:TokyoMetro.Ginza.Shibuya"}
    odpt_fetch.fetch_timetable(params, "secret-key", cache_root=tmp_path)
    assert "secret-key" in http[0]
    for path in tmp_path.iterdir():
        assert "secret-key" not in path.name
        assert "secret-key" not in path.read_text(encoding="utf-8")


# --- ODPTSource ordering ---------------------------------------------------- #

def _table(*times: str) -> list[dict]:
    return [{
        "odpt:railDirection": "odpt.RailDirection:Eastbound",
        "odpt:stationTimetableObject": [
            {"odpt:departureTime": t,
             "odpt:destinationStation": ["odpt.Station:Toei.Shinjuku.Motoyawata"]}
            for t in times
        ],
    }]


def test_post_midnight_trains_rank_after_late_evening_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        odpt_fetch, "_http_get_json", lambda url: _table("05:00", "23:40", "23:55", "00:05")
    )
    line = load_line("shinjuku")
    deps = sources.ODPTSource().departures(
        line, find_station(line, "shinjuku"), datetime(2026, 11, 18, 23, 50), 3
    )
    assert [d.time for d in deps] == ["23:55", "00:05", "05:00"]
    assert deps[0].dest_jp == "本八幡方面"


# --- opt-in switch ---------------------------------------------------------- #

def _never_called(url: str) -> object:
    raise AssertionError(f"went online without opting in: {url}")


def _toei() -> tuple:
    line = load_line("shinjuku")
    return line, find_station(line, "shinjuku")


_NOON = datetime(2026, 11, 18, 12, 0)


def test_offline_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ODPT_KEY", raising=False)
    monkeypatch.setattr(odpt_fetch, "_http_get_json", _never_called)
    _deps, label = sources.get_departures(*_toei(), _NOON)
    assert label == "STATIC"


@pytest.mark.parametrize("via", ["env", "config"])
def test_opting_in_fetches_toei(monkeypatch: pytest.MonkeyPatch, via: str) -> None:
    monkeypatch.delenv("ODPT_KEY", raising=False)
    if via == "env":
        monkeypatch.setenv("JRBOARD_LIVE", "1")
    else:
        monkeypatch.setattr(odpt_fetch, "_config_live", lambda: True)
    monkeypatch.setattr(odpt_fetch, "_http_get_json", lambda url: _table("12:03"))
    deps, label = sources.get_departures(*_toei(), _NOON)
    assert label == "ODPT"
    assert deps[0].time == "12:03"


def test_env_off_overrides_config_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ODPT_KEY", raising=False)
    monkeypatch.setenv("JRBOARD_LIVE", "0")
    monkeypatch.setattr(odpt_fetch, "_config_live", lambda: True)
    monkeypatch.setattr(odpt_fetch, "_http_get_json", _never_called)
    _deps, label = sources.get_departures(*_toei(), _NOON)
    assert label == "STATIC"


def test_opting_in_without_a_key_leaves_other_operators_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ODPT_KEY", raising=False)
    monkeypatch.setenv("JRBOARD_LIVE", "1")
    monkeypatch.setattr(odpt_fetch, "_http_get_json", _never_called)
    line = load_line("ginza")
    _deps, label = sources.get_departures(line, line.stations[0], _NOON)
    assert label == "STATIC"
