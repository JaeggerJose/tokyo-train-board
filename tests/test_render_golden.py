"""Deterministic golden-snapshot tests for the board renderer.

Renders ``render_board`` for three representative lines at a *fixed* datetime
with no ODPT key set, so the static source is fully deterministic. ANSI escape
sequences are stripped before comparison against committed golden files under
``tests/golden``.

Regenerate the golden files after an intentional rendering change with::

    JRBOARD_UPDATE_GOLDEN=1 python -m pytest tests/test_render_golden.py -q
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from jrboard.model import find_station, load_line
from jrboard.render import render_board
from jrboard.sources import get_departures
from jrboard.width import get_visual_width, strip_ansi

# Fixed clock: a weekday (2026-05-31 is a Sunday, so departures use the
# holiday schedule) -- the exact value does not matter as long as it is fixed.
FIXED_NOW = datetime(2026, 5, 31, 8, 0, 0)
BOARD_WIDTH = 60
DEPARTURE_LIMIT = 6

# (line_key, station_key) -> golden filename stem.
CASES = [
    ("yamanote", "shinjuku"),
    ("ginza", "ginza"),
    ("oedo", "tochomae"),
]

_GOLDEN_DIR = Path(__file__).parent / "golden"


def _render_stripped(line_key: str, station_key: str) -> list[str]:
    """Render a board deterministically and strip all ANSI sequences."""
    line = load_line(line_key)
    station = find_station(line, station_key)
    departures, source_label = get_departures(
        line, station, FIXED_NOW, limit=DEPARTURE_LIMIT
    )
    rows = render_board(
        line, station, departures, width=BOARD_WIDTH, source_label=source_label
    )
    return [strip_ansi(row) for row in rows]


def _golden_path(line_key: str, station_key: str) -> Path:
    return _GOLDEN_DIR / f"{line_key}_{station_key}.txt"


@pytest.fixture(autouse=True)
def _no_odpt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the deterministic static source by clearing any ODPT key."""
    monkeypatch.delenv("ODPT_KEY", raising=False)


def _maybe_regenerate() -> bool:
    return os.environ.get("JRBOARD_UPDATE_GOLDEN") == "1"


@pytest.mark.parametrize("line_key,station_key", CASES)
def test_board_matches_golden(line_key: str, station_key: str) -> None:
    rendered = _render_stripped(line_key, station_key)
    path = _golden_path(line_key, station_key)

    if _maybe_regenerate():
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(rendered) + "\n", encoding="utf-8")

    assert path.is_file(), (
        f"missing golden file {path}; regenerate with "
        f"JRBOARD_UPDATE_GOLDEN=1"
    )
    expected = path.read_text(encoding="utf-8").splitlines()
    assert rendered == expected


@pytest.mark.parametrize("line_key,station_key", CASES)
def test_every_row_has_expected_visual_width(
    line_key: str, station_key: str
) -> None:
    # Every framed row must be exactly BOARD_WIDTH visual columns wide so the
    # box-drawing borders line up in a fixed-width terminal.
    rendered = _render_stripped(line_key, station_key)
    for index, row in enumerate(rendered):
        assert get_visual_width(row) == BOARD_WIDTH, (
            f"{line_key}/{station_key} row {index} width "
            f"{get_visual_width(row)} != {BOARD_WIDTH}: {row!r}"
        )
