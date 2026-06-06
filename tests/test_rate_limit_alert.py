"""Tests for the rate-limit alert banner (Claude token-budget warning)."""

from __future__ import annotations

from jrboard.claude_input import rate_limit_alert


def test_no_alert_when_below_threshold():
    assert rate_limit_alert(40.0, 50.0) is None


def test_alert_when_session_critical():
    out = rate_limit_alert(92.0, 30.0, color=False)
    assert out == "⚠速度制限 5h 92%"


def test_alert_when_weekly_critical():
    out = rate_limit_alert(10.0, 95.0, color=False)
    assert out == "⚠速度制限 7d 95%"


def test_alert_picks_the_worst_gauge():
    out = rate_limit_alert(91.0, 99.0, color=False)
    assert "7d 99%" in out


def test_custom_threshold():
    assert rate_limit_alert(75.0, 0.0, threshold=70.0, color=False) == "⚠速度制限 5h 75%"
    assert rate_limit_alert(60.0, 0.0, threshold=70.0) is None


def test_color_wraps_in_ansi():
    out = rate_limit_alert(95.0, 0.0, color=True)
    assert out.startswith("\033[") and out.endswith("\033[0m")


def test_none_inputs_are_safe():
    assert rate_limit_alert(None, None) is None
