"""Tests for jrboard.config: defaults, TOML parsing, favorites round-trip."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jrboard.config import (
    Config,
    config_path,
    favorites_path,
    load_config,
    load_favorites,
    save_favorites,
)


@pytest.fixture(autouse=True)
def _xdg_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point XDG_CONFIG_HOME at an isolated tmp dir for every test."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_paths_respect_xdg_config_home(tmp_path: Path) -> None:
    assert config_path() == str(tmp_path / "jrboard" / "config.toml")
    assert favorites_path() == str(tmp_path / "jrboard" / "favorites.txt")


def test_load_config_defaults_when_no_file() -> None:
    cfg = load_config()
    assert cfg == Config()
    assert cfg.line == "yamanote"
    assert cfg.station == "shinjuku"
    assert cfg.columns == 50
    assert cfg.width == 60
    assert cfg.flap_steps == 22
    assert cfg.flap_delay == pytest.approx(0.08)
    assert cfg.pin_label is True
    assert cfg.color is True
    assert cfg.home is None
    assert cfg.work is None
    assert cfg.leave_buffer_min == 5


def _write_config(body: str) -> None:
    path = Path(config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_load_config_parses_board_and_commute() -> None:
    _write_config(
        """
        [board]
        line = "oedo"
        station = "tochomae"
        columns = 50

        [commute]
        home = ["yamanote", "shinjuku"]
        work = ["yamanote", "tokyo"]
        leave_buffer_min = 7
        """
    )
    cfg = load_config()
    assert cfg.line == "oedo"
    assert cfg.station == "tochomae"
    assert cfg.columns == 50
    assert cfg.home == ("yamanote", "shinjuku")
    assert cfg.work == ("yamanote", "tokyo")
    assert cfg.leave_buffer_min == 7
    # Unspecified keys keep their documented defaults.
    assert cfg.width == 60
    assert cfg.pin_label is True


def test_load_config_malformed_falls_back_to_defaults() -> None:
    _write_config("this is = not valid toml [[[")
    assert load_config() == Config()


def test_load_config_bad_types_and_pairs_use_defaults() -> None:
    _write_config(
        """
        [board]
        columns = "not-an-int"
        color = "off"

        [commute]
        home = ["only-one"]
        work = "not-an-array"
        """
    )
    cfg = load_config()
    assert cfg.columns == 50  # bad int coerced to default
    assert cfg.color is False  # "off" coerces to False
    assert cfg.home is None  # wrong-length array
    assert cfg.work is None  # not an array


def test_favorites_empty_when_no_file() -> None:
    assert load_favorites() == []


def test_favorites_round_trip() -> None:
    favs = [("yamanote", "shinjuku"), ("oedo", "tochomae"), ("ginza", "ginza")]
    save_favorites(favs)
    assert os.path.isfile(favorites_path())
    assert load_favorites() == favs


def test_favorites_skips_blank_and_comment_lines() -> None:
    path = Path(favorites_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# a comment\n"
        "yamanote,shinjuku\n"
        "\n"
        "   \n"
        "oedo,tochomae\n"
        "malformed-line-without-comma\n",
        encoding="utf-8",
    )
    assert load_favorites() == [
        ("yamanote", "shinjuku"),
        ("oedo", "tochomae"),
    ]


def test_save_favorites_creates_missing_dir() -> None:
    # Dir does not exist yet; save must create it.
    assert not os.path.isdir(os.path.dirname(favorites_path()))
    save_favorites([("ginza", "ginza")])
    assert load_favorites() == [("ginza", "ginza")]
