"""StaticSource must respect each line's service hours.

The line JSON says when trains run (``first_train``..``last_train``) and uses a
headway of ``0`` (or a missing hour) for "no trains this hour". The generator
used to ignore both and fill every gap with a 5-minute headway, so the Ginza
line showed trains at 03:00 and the Hokkaido Shinkansen ran every 5 minutes.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from jrboard.model import available_lines, load_line
from jrboard.sources import StaticSource

_DAY = 24 * 60
_WEDNESDAY = (2026, 11, 18)  # an ordinary weekday, not a national holiday


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(*_WEDNESDAY, hour, minute)


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _in_service(clock_min: int, first: int, last: int) -> bool:
    if first <= last:
        return first <= clock_min <= last
    return clock_min >= first or clock_min <= last  # service runs past midnight


@pytest.mark.parametrize("hour, minute", [(0, 45), (1, 10), (3, 0)])
def test_after_last_train_the_board_rolls_over_to_the_first_train(
    hour: int, minute: int
) -> None:
    line = load_line("ginza")  # 05:01 .. 00:39
    deps = StaticSource().departures(line, line.stations[0], _at(hour, minute), 4)
    assert deps, "the board must not go blank between last and first train"
    assert deps[0].time == line.first_train


def test_no_trains_in_an_hour_with_zero_headway() -> None:
    line = load_line("shinkansen-hokkaido")  # weekday hour 8 has headway 0
    deps = StaticSource().departures(line, line.stations[0], _at(8, 0), 6)
    assert not [d.time for d in deps if d.time.startswith("08:")]


def test_late_evening_shows_next_mornings_first_train() -> None:
    line = load_line("shinkansen-tokaido")  # 06:00 .. 22:48
    deps = StaticSource().departures(line, line.stations[0], _at(23, 30), 2)
    assert deps[0].time == line.first_train


def test_times_are_stable_across_refreshes() -> None:
    line = load_line("yamanote")
    station = line.stations[16]
    earlier = StaticSource().departures(line, station, _at(8, 0), 8)
    later = StaticSource().departures(line, station, _at(8, 1), 4)
    still_ahead = [d for d in earlier if _minutes(d.time) >= 8 * 60 + 1]
    assert later == still_ahead[: len(later)]


@pytest.mark.parametrize("key", available_lines())
def test_every_line_stays_inside_its_service_hours(key: str) -> None:
    line = load_line(key)
    first, last = _minutes(line.first_train), _minutes(line.last_train)
    for station in (line.stations[0], line.stations[-1]):
        for hour in (0, 1, 3, 5, 12, 23):
            deps = StaticSource().departures(line, station, _at(hour), 4)
            assert len(deps) == 4, f"{key} {station.name_jp} {hour:02d}:00 is short"
            outside = [
                d.time for d in deps
                if not _in_service(_minutes(d.time), first, last)
            ]
            assert not outside, f"{key} {station.name_jp} @{hour:02d}:00: {outside}"
