"""csl-style context-window bar (``██░░░░░░░░ 27%``) in the jrboard statusline."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from jrboard.claude_input import context_bar

_PAYLOAD = json.dumps({
    "model": {"display_name": "Opus 5"},
    "context_window": {"used_percentage": 27},
    "rate_limits": {
        "five_hour": {"used_percentage": 42},
        "seven_day": {"used_percentage": 18},
    },
})


def _run(*extra: str) -> str:
    env = {k: v for k, v in os.environ.items() if k != "COLUMNS"}
    proc = subprocess.run(
        [sys.executable, "-m", "jrboard", "--claude-stdin", "--no-color", "--tokens",
         "--line", "yamanote", "--station", "shinjuku", *extra],
        input=_PAYLOAD, capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_context_bar_none_is_empty() -> None:
    assert context_bar(None) == ""


def test_context_bar_plain_format() -> None:
    assert context_bar(27.0, color=False) == "██░░░░░░░░ 27%"


def test_context_bar_bounds() -> None:
    assert context_bar(0.0, color=False) == "░░░░░░░░░░ 0%"
    assert context_bar(100.0, color=False) == "██████████ 100%"


def test_context_bar_rounds_like_csl() -> None:
    assert context_bar(29.6, color=False) == "███░░░░░░░ 30%"


def test_context_bar_colours_only_the_bar() -> None:
    assert context_bar(10.0).startswith("\033[38;5;71m█░")
    assert "\033[38;5;179m" in context_bar(75.0)
    assert "\033[38;5;167m" in context_bar(95.0)
    assert context_bar(95.0).endswith("\033[0m 95%")


def test_statusline_unbounded_has_bar_between_model_and_gauge() -> None:
    assert _run("--mode", "statusline").startswith("Opus 5 ██░░░░░░░░ 27% 5h 42%·7d 18%")


def test_jr_board_default_width_shows_bar() -> None:
    # jr-board theme default JR_COLUMNS=72.
    assert _run("--mode", "statusline", "--columns", "72").startswith(
        "Opus 5 ██░░░░░░░░ 27% 5h 42%·7d 18%")


def test_narrow_width_falls_back_to_compact_ctx() -> None:
    # 52 cols => 28 spare: the bar layout (35) does not fit, "ctx 27%" (28) does.
    assert _run("--mode", "statusline", "--columns", "52").startswith(
        "Opus 5 5h 42%·7d 18%·ctx 27%")
