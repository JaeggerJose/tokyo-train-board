"""Tests for the Claude Code STDIN parsing and selection helpers."""

from __future__ import annotations

import json
import re

import pytest

from jrboard.claude_input import (
    ClaudeStatus,
    parse_claude_status,
    pick_by_rotation,
    pick_by_session,
    scope_keys_by_city,
    token_gauge,
)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


# --------------------------------------------------------------------------- #
# parse_claude_status
# --------------------------------------------------------------------------- #
def test_parse_full_blob() -> None:
    raw = json.dumps(
        {
            "session_id": "abc-123",
            "workspace": {"current_dir": "/home/u/proj"},
            "model": {"display_name": "Opus 4.8"},
            "context_window": {"used_percentage": 30.5},
            "rate_limits": {
                "five_hour": {"used_percentage": 42},
                "seven_day": {"used_percentage": 18},
            },
        }
    )
    status = parse_claude_status(raw)
    assert status.session_id == "abc-123"
    assert status.cwd == "/home/u/proj"
    assert status.model == "Opus 4.8"
    assert status.ctx_pct == 30.5
    assert status.session_pct == 42.0
    assert status.weekly_pct == 18.0


def test_parse_cwd_top_level_fallback() -> None:
    status = parse_claude_status(json.dumps({"cwd": "/top/level"}))
    assert status.cwd == "/top/level"


def test_parse_workspace_wins_over_top_level_cwd() -> None:
    raw = json.dumps(
        {"workspace": {"current_dir": "/ws"}, "cwd": "/top"}
    )
    assert parse_claude_status(raw).cwd == "/ws"


def test_parse_garbage_is_all_none() -> None:
    for bad in ("", "   ", "not json", "{broken", "[1,2,3", "null"):
        status = parse_claude_status(bad)
        assert status == ClaudeStatus()


def test_parse_non_string_input_is_all_none() -> None:
    assert parse_claude_status(None) == ClaudeStatus()  # type: ignore[arg-type]
    assert parse_claude_status(123) == ClaudeStatus()  # type: ignore[arg-type]


def test_parse_missing_fields_stay_none() -> None:
    status = parse_claude_status(json.dumps({"session_id": "x"}))
    assert status.session_id == "x"
    assert status.cwd is None
    assert status.model is None
    assert status.ctx_pct is None
    assert status.session_pct is None
    assert status.weekly_pct is None


def test_parse_wrong_typed_fields_stay_none() -> None:
    raw = json.dumps(
        {
            "session_id": 999,  # not a string
            "context_window": {"used_percentage": "oops"},
            "rate_limits": {"five_hour": "nope"},
        }
    )
    status = parse_claude_status(raw)
    assert status.session_id is None
    assert status.ctx_pct is None
    assert status.session_pct is None


def test_parse_clamps_out_of_range_pct() -> None:
    raw = json.dumps(
        {
            "context_window": {"used_percentage": 150},
            "rate_limits": {
                "five_hour": {"used_percentage": -5},
                "seven_day": {"used_percentage": 100},
            },
        }
    )
    status = parse_claude_status(raw)
    assert status.ctx_pct == 100.0
    assert status.session_pct == 0.0
    assert status.weekly_pct == 100.0


def test_parse_never_raises() -> None:
    # A deeply nested wrong shape must still return a status, not raise.
    raw = json.dumps({"rate_limits": {"five_hour": {"used_percentage": True}}})
    status = parse_claude_status(raw)
    assert status.session_pct is None  # bool rejected


# --------------------------------------------------------------------------- #
# pick_by_session
# --------------------------------------------------------------------------- #
KEYS = ["yamanote", "chuo", "oedo", "ginza", "marunouchi"]


def test_pick_by_session_deterministic_same_session() -> None:
    a = pick_by_session(KEYS, "session-42")
    b = pick_by_session(KEYS, "session-42")
    assert a == b
    assert a in KEYS


def test_pick_by_session_stable_across_calls() -> None:
    # Stability is the whole point: a session keeps its line over many renders.
    picks = {pick_by_session(KEYS, "stable-sid") for _ in range(50)}
    assert len(picks) == 1


def test_pick_by_session_distributes() -> None:
    # Many distinct sessions should hit more than one key in the pool.
    seen = {pick_by_session(KEYS, f"s{i}") for i in range(200)}
    assert len(seen) >= 2


def test_pick_by_session_empty_pool_raises() -> None:
    with pytest.raises(ValueError):
        pick_by_session([], "sid")


def test_pick_by_session_no_session_id_is_first() -> None:
    assert pick_by_session(KEYS, "") == KEYS[0]


# --------------------------------------------------------------------------- #
# pick_by_rotation
# --------------------------------------------------------------------------- #
def test_pick_by_rotation_advances_with_time() -> None:
    period = 30
    first = pick_by_rotation(KEYS, 0.0, period)
    same_bucket = pick_by_rotation(KEYS, 29.0, period)
    next_bucket = pick_by_rotation(KEYS, 30.0, period)
    assert first == same_bucket
    assert first != next_bucket or len(KEYS) == 1


def test_pick_by_rotation_wraps_pool() -> None:
    period = 10
    # Bucket 0 and bucket len(KEYS) land on the same key (wrap-around).
    at_zero = pick_by_rotation(KEYS, 0.0, period)
    at_wrap = pick_by_rotation(KEYS, float(period * len(KEYS)), period)
    assert at_zero == at_wrap


def test_pick_by_rotation_empty_pool_raises() -> None:
    with pytest.raises(ValueError):
        pick_by_rotation([], 0.0, 30)


def test_pick_by_rotation_nonpositive_period_safe() -> None:
    # period <= 0 is treated as 1; must not raise (no ZeroDivisionError).
    assert pick_by_rotation(KEYS, 5.0, 0) in KEYS


# --------------------------------------------------------------------------- #
# scope_keys_by_city
# --------------------------------------------------------------------------- #
def test_scope_keys_by_city_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeLine:
        def __init__(self, city: str) -> None:
            self.city = city

    cities = {
        "yamanote": "Tokyo",
        "osaka-loop": "Osaka",
        "chuo": "Tokyo",
    }

    def fake_load(key: str) -> _FakeLine:
        return _FakeLine(cities[key])

    monkeypatch.setattr("jrboard.model.load_line", fake_load)
    out = scope_keys_by_city(list(cities), "tokyo")
    assert out == ["yamanote", "chuo"]


def test_scope_keys_by_city_empty_match_returns_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeLine:
        city = "Tokyo"

    monkeypatch.setattr("jrboard.model.load_line", lambda k: _FakeLine())
    keys = ["yamanote", "chuo"]
    assert scope_keys_by_city(keys, "atlantis") == keys


def test_scope_keys_by_city_no_city_returns_original() -> None:
    keys = ["a", "b"]
    assert scope_keys_by_city(keys, None) == keys
    assert scope_keys_by_city(keys, "") == keys
    assert scope_keys_by_city(keys, "   ") == keys


def test_scope_keys_by_city_skips_unloadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_load(key: str):
        if key == "bad":
            raise ValueError("boom")

        class _L:
            city = "Tokyo"

        return _L()

    monkeypatch.setattr("jrboard.model.load_line", fake_load)
    out = scope_keys_by_city(["bad", "good"], "tokyo")
    assert out == ["good"]


# --------------------------------------------------------------------------- #
# token_gauge
# --------------------------------------------------------------------------- #
def test_token_gauge_all_none_is_empty() -> None:
    assert token_gauge(None, None, None) == ""


def test_token_gauge_basic_format() -> None:
    seg = token_gauge(42.0, 18.0, color=False)
    assert seg == "5h 42% · 7d 18%"


def test_token_gauge_includes_ctx() -> None:
    seg = token_gauge(42.0, 18.0, 30.0, color=False)
    assert "ctx 30%" in seg
    assert seg == "5h 42% · 7d 18% · ctx 30%"


def test_token_gauge_partial() -> None:
    assert token_gauge(50.0, None, color=False) == "5h 50%"
    assert token_gauge(None, 60.0, color=False) == "7d 60%"
    assert token_gauge(None, None, 12.0, color=False) == "ctx 12%"


def test_token_gauge_rounds() -> None:
    assert token_gauge(42.6, None, color=False) == "5h 43%"


def test_token_gauge_color_thresholds() -> None:
    green = token_gauge(10.0, None, color=True)
    yellow = token_gauge(75.0, None, color=True)
    red = token_gauge(95.0, None, color=True)
    assert "\033[38;5;71m" in green
    assert "\033[38;5;179m" in yellow
    assert "\033[38;5;167m" in red
    # Stripping ANSI recovers the plain text.
    assert _strip_ansi(red) == "5h 95%"


def test_token_gauge_threshold_boundaries() -> None:
    # 70 -> yellow, 90 -> red, 69 -> green.
    assert "\033[38;5;71m" in token_gauge(69.0, None, color=True)
    assert "\033[38;5;179m" in token_gauge(70.0, None, color=True)
    assert "\033[38;5;167m" in token_gauge(90.0, None, color=True)


def test_token_gauge_color_false_is_plain() -> None:
    assert "\033[" not in token_gauge(95.0, 95.0, 95.0, color=False)
