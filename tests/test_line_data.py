"""Integrity checks for every bundled line data file."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from jrboard.model import available_lines, load_line

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "apply_colors.py"
_spec = importlib.util.spec_from_file_location("apply_colors", _SCRIPT)
apply_colors = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(apply_colors)

SHINKANSEN = [
    "shinkansen-tokaido", "shinkansen-sanyo", "shinkansen-kyushu",
    "shinkansen-nishikyushu", "shinkansen-hokkaido", "shinkansen-tohoku",
    "shinkansen-joetsu", "shinkansen-hokuriku", "shinkansen-yamagata",
    "shinkansen-akita",
]
NEW_LINES = [
    "osaka-chuo", "yurikamome", "tokyu-toyoko", "keio", "keiyo",
    "yokohama-blue", "nagoya-higashiyama", "fukuoka-kuko",
]


def test_new_lines_are_bundled() -> None:
    keys = set(available_lines())
    assert set(SHINKANSEN + NEW_LINES) <= keys


def test_all_shinkansen_grouped_under_one_city() -> None:
    cities = {key: load_line(key).city for key in available_lines()}
    assert sorted(k for k, c in cities.items() if c == "Shinkansen") == sorted(SHINKANSEN)


def test_new_cities() -> None:
    assert load_line("yokohama-blue").city == "Yokohama"
    assert load_line("nagoya-higashiyama").city == "Nagoya"
    assert load_line("fukuoka-kuko").city == "Fukuoka"


@pytest.mark.parametrize("key", available_lines())
def test_station_ids_unique(key: str) -> None:
    ids = [s.id for s in load_line(key).stations]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("key", available_lines())
def test_colour_matches_official_table(key: str) -> None:
    line = load_line(key)
    assert key in apply_colors.OFFICIAL, f"{key} missing from scripts/apply_colors.py"
    hex_code, name = apply_colors.OFFICIAL[key]
    expected = apply_colors.build_color(hex_code, name)
    assert (line.hex, line.ansi_fg, line.ansi_bg) == (
        expected["hex"], expected["ansi_fg"], expected["ansi_bg"],
    )


def test_cli_help_renders() -> None:
    import subprocess
    import sys

    proc = subprocess.run([sys.executable, "-m", "jrboard", "--help"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "--by-project" in proc.stdout
