"""Model name in the jrboard statusline (jr-board / jr-timetable themes)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from jrboard.claude_input import model_label

_PAYLOAD = json.dumps({
    "session_id": "abc",
    "model": {"id": "claude-opus-5", "display_name": "Opus 5"},
    "context_window": {"used_percentage": 30},
    "rate_limits": {
        "five_hour": {"used_percentage": 42},
        "seven_day": {"used_percentage": 18},
    },
})


def _run(*extra: str, payload: str = _PAYLOAD) -> str:
    env = {k: v for k, v in os.environ.items() if k != "COLUMNS"}
    proc = subprocess.run(
        [sys.executable, "-m", "jrboard", "--claude-stdin", "--no-color",
         "--line", "yamanote", "--station", "shinjuku", *extra],
        input=payload, capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_model_label_none_is_empty() -> None:
    assert model_label(None) == ""
    assert model_label("") == ""


def test_model_label_plain() -> None:
    assert model_label("Opus 5", color=False) == "Opus 5"


def test_model_label_colored_wraps_ansi() -> None:
    label = model_label("Opus 5", color=True)
    assert "Opus 5" in label and label.startswith("\033[") and label.endswith("\033[0m")


def test_model_label_dropped_when_too_narrow() -> None:
    assert model_label("Opus 5", color=False, max_width=5) == ""
    assert model_label("Opus 5", color=False, max_width=6) == "Opus 5"


def test_statusline_tokens_shows_model_first() -> None:
    out = _run("--mode", "statusline", "--tokens")
    assert out.startswith("Opus 5 5h 42%")


def test_minitable_tokens_shows_model_in_header() -> None:
    head = _run("--mode", "minitable", "--tokens").split("\n")[0]
    assert "Opus 5 5h 42%" in head


def test_statusline_model_only_when_no_rate_limits() -> None:
    payload = json.dumps({"model": {"display_name": "Sonnet 5"}})
    out = _run("--mode", "statusline", "--tokens", payload=payload)
    assert out.startswith("Sonnet 5 ")


def test_minitable_default_width_trades_ctx_for_model() -> None:
    # jr-timetable's default JR_COLUMNS=40 leaves 24 cols for the header gauge.
    head = _run("--mode", "minitable", "--tokens", "--columns", "40").split("\n")[0]
    assert "Opus 5 5h 42%·7d 18%" in head
    assert "ctx" not in head


def test_narrow_statusline_keeps_gauge_over_model() -> None:
    out = _run("--mode", "statusline", "--tokens", "--columns", "30")
    assert out.startswith("5h 42%")
    assert "Opus 5" not in out


def test_statusline_without_tokens_has_no_model() -> None:
    assert "Opus 5" not in _run("--mode", "statusline")
