"""Tests for jrboard.model: loading, station lookup, neighbour wrapping."""

from __future__ import annotations

import pytest

from jrboard.model import (
    Line,
    Station,
    available_lines,
    find_station,
    load_line,
    neighbors,
)


def test_available_lines_includes_bundled_data() -> None:
    keys = available_lines()
    assert "yamanote" in keys
    assert "asakusa" in keys


def test_load_line_yamanote_is_loop() -> None:
    line = load_line("yamanote")
    assert isinstance(line, Line)
    assert line.key == "yamanote"
    assert line.loop is True
    assert line.symbol == "JY"
    assert len(line.stations) == 30
    assert len(line.directions) == 2


def test_load_line_asakusa_is_linear() -> None:
    line = load_line("asakusa")
    assert line.loop is False
    assert line.symbol == "A"
    assert len(line.stations) == 20


def test_load_line_is_case_insensitive() -> None:
    assert load_line("YAMANOTE").key == "yamanote"


def test_load_line_unknown_lists_available() -> None:
    with pytest.raises(ValueError) as exc:
        load_line("nonexistent-line")
    message = str(exc.value)
    assert "nonexistent-line" in message
    assert "yamanote" in message  # helpful list of available keys


def test_find_station_by_name_en_case_insensitive() -> None:
    line = load_line("yamanote")
    st = find_station(line, "shinjuku")
    assert isinstance(st, Station)
    assert st.name_en == "Shinjuku"
    assert st.number == "17"


def test_find_station_by_id_and_number() -> None:
    line = load_line("yamanote")
    assert find_station(line, "JY01").name_en == "Tokyo"
    assert find_station(line, "01").name_en == "Tokyo"
    # number without leading zero should also match
    assert find_station(line, "1").name_en == "Tokyo"


def test_find_station_unknown_raises() -> None:
    line = load_line("yamanote")
    with pytest.raises(ValueError):
        find_station(line, "atlantis")


def test_neighbors_middle_station() -> None:
    line = load_line("yamanote")
    shinjuku = find_station(line, "shinjuku")  # JY17
    prev_st, curr_st, next_st = neighbors(line, shinjuku)
    assert curr_st.name_en == "Shinjuku"
    assert prev_st is not None and prev_st.name_en == "Shin-Okubo"
    assert next_st is not None and next_st.name_en == "Yoyogi"


def test_neighbors_loop_wraps_at_ends() -> None:
    line = load_line("yamanote")
    first = line.stations[0]   # Tokyo
    last = line.stations[-1]   # Yurakucho
    # On a loop the first station's prev wraps to the last station.
    prev_of_first, _, next_of_first = neighbors(line, first)
    assert prev_of_first is not None and prev_of_first.id == last.id
    # And the last station's next wraps back to the first.
    _, _, next_of_last = neighbors(line, last)
    assert next_of_last is not None and next_of_last.id == first.id


def test_neighbors_linear_endpoints_are_none() -> None:
    line = load_line("asakusa")
    first = line.stations[0]   # Nishi-magome
    last = line.stations[-1]   # Oshiage
    prev_of_first, _, _ = neighbors(line, first)
    assert prev_of_first is None
    _, _, next_of_last = neighbors(line, last)
    assert next_of_last is None
