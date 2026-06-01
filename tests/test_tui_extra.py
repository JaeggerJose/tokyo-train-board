"""Unit tests for the TUI's pure colour / ANSI / city-grouping helpers.

The curses layer can't run headless, so these pure functions carry the test
value for the colour + grouping work.
"""

from __future__ import annotations

from jrboard.tui import (
    grouped_display_rows,
    order_by_city,
    parse_ansi_runs,
    rgb_to_xterm256,
)


def test_rgb_to_xterm256_in_range() -> None:
    for rgb in [(0, 0, 0), (255, 255, 255), (154, 205, 50), (255, 149, 0), (0, 103, 192)]:
        idx = rgb_to_xterm256(*rgb)
        assert 0 <= idx <= 255


def test_rgb_to_xterm256_greys_use_grayscale_ramp() -> None:
    # A mid grey should map into the grayscale ramp (232-255) or a cube grey.
    idx = rgb_to_xterm256(128, 128, 128)
    assert 232 <= idx <= 255 or idx == 145  # ramp, or the cube's mid grey


def test_rgb_to_xterm256_clamps_out_of_range() -> None:
    assert 0 <= rgb_to_xterm256(-10, 300, 128) <= 255


def test_parse_ansi_runs_truecolor_fg() -> None:
    runs = parse_ansi_runs("\033[38;2;154;205;50mAB\033[0mCD")
    assert runs[0][0] == "AB"
    assert runs[0][1] == rgb_to_xterm256(154, 205, 50)
    assert runs[0][2] is None
    assert runs[-1] == ("CD", None, None)


def test_parse_ansi_runs_indexed_and_bg() -> None:
    runs = parse_ansi_runs("\033[48;5;208m\033[38;5;16m X \033[0m")
    seg, fg, bg = runs[0]
    assert seg == " X "
    assert bg == 208
    assert fg == 16


def test_parse_ansi_runs_plain_text() -> None:
    assert parse_ansi_runs("hello") == [("hello", None, None)]


def test_order_by_city_tokyo_first_then_alpha() -> None:
    cities = {
        "ginza": "Tokyo",
        "osaka-loop": "Osaka",
        "kyoto-tozai": "Kyoto",
        "yamanote": "Tokyo",
    }
    ordered = order_by_city(["ginza", "osaka-loop", "kyoto-tozai", "yamanote"], cities)
    # Tokyo lines come first (stable, original order), then Kyoto, then Osaka.
    assert ordered == ("ginza", "yamanote", "kyoto-tozai", "osaka-loop")


def test_grouped_display_rows_inserts_headers() -> None:
    cities = {"ginza": "Tokyo", "yamanote": "Tokyo", "osaka-loop": "Osaka"}
    rows = grouped_display_rows(["ginza", "yamanote", "osaka-loop"], cities)
    assert rows[0] == ("header", "Tokyo")
    # Line items carry their index within the view (what the cursor selects).
    line_items = [r for r in rows if r[0] == "line"]
    assert line_items == [("line", "ginza", 0), ("line", "yamanote", 1), ("line", "osaka-loop", 2)]
    # A header appears exactly once per distinct city.
    headers = [r[1] for r in rows if r[0] == "header"]
    assert headers == ["Tokyo", "Osaka"]


def test_grouped_display_rows_empty_view() -> None:
    assert grouped_display_rows([], {}) == []
