"""Tests for the pure (non-curses) helpers in :mod:`jrboard.tui`.

These cover the logic that the interactive loop delegates to: fuzzy filtering,
selection clamping, station stepping (with loop wrap and linear endpoints),
favourite toggling, and favourite cycling. None of these touch a TTY, so they
run headless under pytest.
"""

from __future__ import annotations

import pytest

from jrboard.model import find_station, load_line
from jrboard.tui import (
    clamp_index,
    fuzzy_filter,
    line_labels,
    next_favorite_index,
    step_station_key,
    toggle_favorite,
)

KEYS = ("yamanote", "oedo", "ginza", "marunouchi", "chuo")


# --------------------------------------------------------------------------- #
# fuzzy_filter                                                                 #
# --------------------------------------------------------------------------- #


def test_fuzzy_filter_empty_query_returns_all() -> None:
    assert fuzzy_filter(KEYS, "") == KEYS
    assert fuzzy_filter(KEYS, "   ") == KEYS


def test_fuzzy_filter_is_subsequence_not_substring() -> None:
    # "ymn" is a subsequence of "yamanote" but not a contiguous substring.
    assert fuzzy_filter(KEYS, "ymn") == ("yamanote",)


def test_fuzzy_filter_case_insensitive() -> None:
    assert fuzzy_filter(KEYS, "GINZA") == ("ginza",)


def test_fuzzy_filter_preserves_input_order() -> None:
    # Both contain the subsequence 'o'... ensure order from KEYS is kept.
    result = fuzzy_filter(KEYS, "o")
    assert result == tuple(k for k in KEYS if "o" in k)


def test_fuzzy_filter_no_match_returns_empty() -> None:
    assert fuzzy_filter(KEYS, "zzzz") == ()


def test_fuzzy_filter_matches_label() -> None:
    labels = {"oedo": "都営大江戸線"}
    # Query the JP label even though the key wouldn't match.
    assert "oedo" in fuzzy_filter(KEYS, "大江戸", labels=labels)


# --------------------------------------------------------------------------- #
# clamp_index                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "index,length,expected",
    [
        (0, 5, 0),
        (3, 5, 3),
        (4, 5, 4),
        (5, 5, 4),       # past end -> last
        (99, 5, 4),
        (-1, 5, 0),      # negative -> first
        (-99, 5, 0),
        (0, 0, -1),      # empty -> -1
        (3, 0, -1),
    ],
)
def test_clamp_index(index: int, length: int, expected: int) -> None:
    assert clamp_index(index, length) == expected


# --------------------------------------------------------------------------- #
# step_station_key                                                             #
# --------------------------------------------------------------------------- #


def test_step_station_forward_and_back() -> None:
    line = load_line("yamanote")
    start = line.stations[2]
    fwd = step_station_key(line, start, +1)
    back = step_station_key(line, start, -1)
    assert fwd == line.stations[3].id
    assert back == line.stations[1].id


def test_step_station_delta_zero_is_noop() -> None:
    line = load_line("yamanote")
    st = line.stations[0]
    assert step_station_key(line, st, 0) == st.id


def test_step_station_loop_wraps_at_ends() -> None:
    line = load_line("yamanote")
    assert line.loop, "yamanote is expected to be a loop line"
    first = line.stations[0]
    last = line.stations[-1]
    # Stepping back from the first wraps to the last, and vice versa.
    assert step_station_key(line, first, -1) == last.id
    assert step_station_key(line, last, +1) == first.id


def test_step_station_linear_endpoints_clamp() -> None:
    # Find a non-loop line in the dataset to verify endpoint behaviour.
    from jrboard.model import available_lines

    linear = None
    for key in available_lines():
        candidate = load_line(key)
        if not candidate.loop:
            linear = candidate
            break
    assert linear is not None, "expected at least one linear line in data"

    first = linear.stations[0]
    last = linear.stations[-1]
    # Stepping before the first / after the last leaves the station unchanged.
    assert step_station_key(linear, first, -1) == first.id
    assert step_station_key(linear, last, +1) == last.id


def test_step_station_roundtrip_returns_id_findable() -> None:
    # The returned key must be something find_station accepts.
    line = load_line("yamanote")
    st = line.stations[5]
    key = step_station_key(line, st, +1)
    found = find_station(line, key)
    assert found.id == line.stations[6].id


# --------------------------------------------------------------------------- #
# toggle_favorite                                                              #
# --------------------------------------------------------------------------- #


def test_toggle_favorite_adds_when_absent() -> None:
    favs: list[tuple[str, str]] = [("yamanote", "shinjuku")]
    out = toggle_favorite(favs, ("oedo", "tochomae"))
    assert out == [("yamanote", "shinjuku"), ("oedo", "tochomae")]


def test_toggle_favorite_removes_when_present() -> None:
    favs = [("yamanote", "shinjuku"), ("oedo", "tochomae")]
    out = toggle_favorite(favs, ("yamanote", "shinjuku"))
    assert out == [("oedo", "tochomae")]


def test_toggle_favorite_does_not_mutate_input() -> None:
    favs = [("yamanote", "shinjuku")]
    snapshot = list(favs)
    toggle_favorite(favs, ("oedo", "tochomae"))
    toggle_favorite(favs, ("yamanote", "shinjuku"))
    assert favs == snapshot  # original untouched (immutability)


def test_toggle_favorite_is_idempotent_pair() -> None:
    favs: list[tuple[str, str]] = []
    once = toggle_favorite(favs, ("ginza", "ginza"))
    twice = toggle_favorite(once, ("ginza", "ginza"))
    assert once == [("ginza", "ginza")]
    assert twice == []


# --------------------------------------------------------------------------- #
# next_favorite_index                                                          #
# --------------------------------------------------------------------------- #


def test_next_favorite_index_empty_is_minus_one() -> None:
    assert next_favorite_index([], -1) == -1
    assert next_favorite_index([], 3) == -1


def test_next_favorite_index_wraps() -> None:
    favs = [("a", "1"), ("b", "2"), ("c", "3")]
    assert next_favorite_index(favs, -1) == 0
    assert next_favorite_index(favs, 0) == 1
    assert next_favorite_index(favs, 2) == 0  # wrap around


# --------------------------------------------------------------------------- #
# line_labels                                                                  #
# --------------------------------------------------------------------------- #


def test_line_labels_maps_known_keys() -> None:
    labels = line_labels(["yamanote"])
    assert labels["yamanote"] == load_line("yamanote").name_jp


def test_line_labels_skips_unknown_keys() -> None:
    labels = line_labels(["definitely-not-a-line"])
    assert labels == {}
