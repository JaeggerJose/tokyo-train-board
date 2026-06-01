"""Tests for the commute guardian decision logic and renderers.

These tests use lightweight fakes for the config, the line/station model, and
the departure source so the pure logic is exercised without a real clock,
network, or JSON data. Real time is never read: ``now`` is always injected.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from jrboard.commute import (
    CommuteAdvice,
    commute_advice,
    commute_oneline,
    direction_toward,
    is_morning,
    leave_in_min,
    render_commute,
    resolve_leg,
)


# --------------------------------------------------------------------------- #
# Fakes mirroring the real model/config shapes (frozen, immutable).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FakeStation:
    id: str
    number: str
    name_jp: str
    kana: str
    name_en: str
    odpt_station: str = ""


@dataclass(frozen=True)
class FakeDirection:
    id: str
    name_jp: str
    via_jp: str
    track: str


@dataclass(frozen=True)
class FakeLine:
    key: str
    name_jp: str
    name_en: str
    symbol: str
    loop: bool
    ansi_fg: str
    ansi_bg: str
    stations: tuple
    directions: tuple


@dataclass(frozen=True)
class FakeDep:
    time: str
    kind_jp: str
    dest_jp: str
    track: str
    direction: str


@dataclass(frozen=True)
class FakeConfig:
    home: tuple | None = None
    work: tuple | None = None
    leave_buffer_min: int = 5


# A short straight (non-loop) line: A(0) - B(1) - C(2) - D(3).
_STATIONS = (
    FakeStation("L1", "1", "甲", "こう", "Alpha"),
    FakeStation("L2", "2", "乙", "おつ", "Bravo"),
    FakeStation("L3", "3", "丙", "へい", "Charlie"),
    FakeStation("L4", "4", "丁", "てい", "Delta"),
)
_DIRECTIONS = (
    FakeDirection("forward", "下り", "Delta方面", "1"),
    FakeDirection("backward", "上り", "Alpha方面", "2"),
)
LINE = FakeLine(
    key="testline",
    name_jp="テスト線",
    name_en="Test Line",
    symbol="T",
    loop=False,
    ansi_fg="\033[38;5;34m",
    ansi_bg="\033[48;5;28m",
    stations=_STATIONS,
    directions=_DIRECTIONS,
)


def _loader(_key: str) -> FakeLine:
    return LINE


def _finder(line: FakeLine, key: str) -> FakeStation:
    for st in line.stations:
        if key.lower() in (st.name_en.lower(), st.id.lower(), st.number):
            return st
    raise ValueError(f"no station {key!r}")


def _make_source(deps: list[FakeDep], label: str = "STATIC"):
    def _source(_line, _station, _now, _limit):
        return list(deps), label

    return _source


MORNING = dt.datetime(2026, 5, 31, 8, 0, 0)
EVENING = dt.datetime(2026, 5, 31, 18, 0, 0)


# --------------------------------------------------------------------------- #
# is_morning / resolve_leg
# --------------------------------------------------------------------------- #


def test_is_morning_threshold() -> None:
    assert is_morning(dt.datetime(2026, 5, 31, 0, 0)) is True
    assert is_morning(dt.datetime(2026, 5, 31, 13, 59)) is True
    assert is_morning(dt.datetime(2026, 5, 31, 14, 0)) is False
    assert is_morning(dt.datetime(2026, 5, 31, 23, 59)) is False


def test_is_morning_custom_boundary() -> None:
    assert is_morning(dt.datetime(2026, 5, 31, 11, 0), before_hour=12) is True
    assert is_morning(dt.datetime(2026, 5, 31, 12, 0), before_hour=12) is False


def test_resolve_leg_morning_is_home_to_work() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"))
    origin, dest, heading = resolve_leg(cfg, MORNING)
    assert origin == ("testline", "alpha")
    assert dest == ("testline", "delta")
    assert heading == "Home -> Work"


def test_resolve_leg_evening_is_work_to_home() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"))
    origin, dest, heading = resolve_leg(cfg, EVENING)
    assert origin == ("testline", "delta")
    assert dest == ("testline", "alpha")
    assert heading == "Work -> Home"


def test_resolve_leg_none_when_unconfigured() -> None:
    assert resolve_leg(FakeConfig(), MORNING) is None
    assert resolve_leg(FakeConfig(home=("l", "s")), MORNING) is None
    assert resolve_leg(FakeConfig(work=("l", "s")), MORNING) is None


# --------------------------------------------------------------------------- #
# direction_toward
# --------------------------------------------------------------------------- #


def test_direction_forward_when_destination_index_higher() -> None:
    alpha, delta = _STATIONS[0], _STATIONS[3]
    assert direction_toward(LINE, alpha, delta) == "forward"


def test_direction_backward_when_destination_index_lower() -> None:
    alpha, delta = _STATIONS[0], _STATIONS[3]
    assert direction_toward(LINE, delta, alpha) == "backward"


def test_direction_none_for_same_station() -> None:
    alpha = _STATIONS[0]
    assert direction_toward(LINE, alpha, alpha) is None


def test_direction_loop_picks_shorter_arc() -> None:
    # 6-station ring: 0..5. Inner = forward(idx up), outer = backward.
    ring = tuple(
        FakeStation(f"R{i}", str(i), f"駅{i}", "", f"Stn{i}") for i in range(6)
    )
    loop_dirs = (
        FakeDirection("inner", "内回り", "", "1"),
        FakeDirection("outer", "外回り", "", "2"),
    )
    loop = FakeLine(
        key="ring", name_jp="環", name_en="Ring", symbol="R", loop=True,
        ansi_fg="", ansi_bg="", stations=ring, directions=loop_dirs,
    )
    # 0 -> 2: short arc is forward.
    assert direction_toward(loop, ring[0], ring[2]) == "inner"
    # 0 -> 4: short arc is backward (0 -> 5 -> 4).
    assert direction_toward(loop, ring[0], ring[4]) == "outer"


# --------------------------------------------------------------------------- #
# leave_in_min
# --------------------------------------------------------------------------- #


def test_leave_in_min_subtracts_buffer() -> None:
    now = dt.datetime(2026, 5, 31, 8, 0)
    # train at 08:12 -> 12 min away, buffer 5 -> leave in 7.
    assert leave_in_min("08:12", now, 5) == 7


def test_leave_in_min_never_negative() -> None:
    now = dt.datetime(2026, 5, 31, 8, 10)
    # train at 08:12 -> 2 min away, buffer 5 -> would be -3, clamped to 0.
    assert leave_in_min("08:12", now, 5) == 0


def test_leave_in_min_zero_when_train_now() -> None:
    now = dt.datetime(2026, 5, 31, 8, 0)
    assert leave_in_min("08:00", now, 0) == 0


def test_leave_in_min_malformed_time_is_zero() -> None:
    now = dt.datetime(2026, 5, 31, 8, 0)
    assert leave_in_min("not-a-time", now, 5) == 0


# --------------------------------------------------------------------------- #
# commute_advice
# --------------------------------------------------------------------------- #


def _advice(cfg: FakeConfig, now: dt.datetime, deps: list[FakeDep], **kw):
    return commute_advice(
        cfg,
        now,
        line_loader=_loader,
        station_finder=_finder,
        departure_source=_make_source(deps),
        **kw,
    )


def test_advice_none_when_unconfigured() -> None:
    assert _advice(FakeConfig(), MORNING, []) is None


def test_advice_morning_picks_home_to_work_direction() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"),
                     leave_buffer_min=5)
    deps = [
        FakeDep("08:12", "各停", "Delta方面", "1", "forward"),
        FakeDep("08:10", "各停", "Alpha方面", "2", "backward"),
        FakeDep("08:20", "各停", "Delta方面", "1", "forward"),
    ]
    advice = _advice(cfg, MORNING, deps)
    assert advice is not None
    assert advice.heading == "Home -> Work"
    assert advice.station.name_en == "Alpha"
    assert advice.dest_station.name_en == "Delta"
    # Only the forward (toward Delta) departures survive direction filtering.
    assert [d.direction for d in advice.trains] == ["forward", "forward"]
    # Soonest forward train 08:12, now 08:00 -> 12 - 5 buffer = 7.
    assert advice.leave_in_min == 7


def test_advice_evening_picks_work_to_home_direction() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"),
                     leave_buffer_min=5)
    deps = [
        FakeDep("18:09", "各停", "Alpha方面", "2", "backward"),
        FakeDep("18:08", "各停", "Delta方面", "1", "forward"),
    ]
    advice = _advice(cfg, EVENING, deps)
    assert advice is not None
    assert advice.heading == "Work -> Home"
    assert advice.station.name_en == "Delta"
    assert advice.dest_station.name_en == "Alpha"
    assert [d.direction for d in advice.trains] == ["backward"]
    # 18:09 - 18:00 = 9, minus buffer 5 = 4.
    assert advice.leave_in_min == 4


def test_advice_leave_clamped_to_zero_when_train_imminent() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"),
                     leave_buffer_min=5)
    now = dt.datetime(2026, 5, 31, 8, 10)
    deps = [FakeDep("08:12", "各停", "Delta方面", "1", "forward")]
    advice = _advice(cfg, now, deps)
    assert advice is not None
    assert advice.leave_in_min == 0


def test_advice_unknown_station_returns_none() -> None:
    cfg = FakeConfig(home=("testline", "nope"), work=("testline", "delta"))
    advice = _advice(cfg, MORNING, [])
    assert advice is None


def test_advice_no_trains_when_source_empty() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"))
    advice = _advice(cfg, MORNING, [])
    assert advice is not None
    assert advice.trains == []
    assert advice.leave_in_min == 0


def test_advice_respects_limit() -> None:
    cfg = FakeConfig(home=("testline", "alpha"), work=("testline", "delta"))
    deps = [
        FakeDep(f"08:{m:02d}", "各停", "Delta方面", "1", "forward")
        for m in (10, 12, 14, 16, 18, 20)
    ]
    advice = _advice(cfg, MORNING, deps, limit=3)
    assert advice is not None
    assert len(advice.trains) == 3


# --------------------------------------------------------------------------- #
# render_commute / commute_oneline
# --------------------------------------------------------------------------- #


def _build_advice() -> CommuteAdvice:
    return CommuteAdvice(
        line=LINE,
        station=_STATIONS[0],
        heading="Home -> Work",
        trains=[FakeDep("08:12", "各停", "Delta方面", "1", "forward")],
        leave_in_min=7,
        source_label="STATIC",
        dest_station=_STATIONS[3],
    )


def test_render_commute_includes_headline_and_source() -> None:
    advice = _build_advice()
    out = render_commute(advice, MORNING, width=60)
    blob = "\n".join(out)
    assert "leave in 7" in blob
    assert "STATIC" in blob
    assert "Home -> Work" in blob
    # Framed: first and last lines are the box top border.
    assert out[0].startswith("+") and out[-1].startswith("+")


def test_render_commute_leave_now_when_zero() -> None:
    advice = _build_advice()
    zero = CommuteAdvice(
        line=advice.line, station=advice.station, heading=advice.heading,
        trains=advice.trains, leave_in_min=0, source_label="STATIC",
        dest_station=advice.dest_station,
    )
    blob = "\n".join(render_commute(zero, dt.datetime(2026, 5, 31, 8, 10)))
    assert "NOW" in blob


def test_render_commute_unconfigured_is_safe() -> None:
    out = render_commute(None, MORNING)
    assert isinstance(out, list) and out
    assert "not configured" in "\n".join(out)


def test_oneline_compact_with_leave_minutes() -> None:
    line = commute_oneline(_build_advice(), MORNING)
    assert line.startswith("[T] Home->Work")
    assert "leave in 7m" in line
    assert "08:12" in line


def test_oneline_leave_now() -> None:
    advice = _build_advice()
    zero = CommuteAdvice(
        line=advice.line, station=advice.station, heading=advice.heading,
        trains=advice.trains, leave_in_min=0, source_label="STATIC",
        dest_station=advice.dest_station,
    )
    assert "leave NOW" in commute_oneline(zero, MORNING)


def test_oneline_unconfigured() -> None:
    assert commute_oneline(None, MORNING) == "commute: not configured"


def test_oneline_no_train() -> None:
    advice = CommuteAdvice(
        line=LINE, station=_STATIONS[0], heading="Home -> Work", trains=[],
        leave_in_min=0, source_label="STATIC", dest_station=_STATIONS[3],
    )
    assert "no train" in commute_oneline(advice, MORNING)
