"""Tests for the statusLine self-installer (jrboard.install)."""

from __future__ import annotations

import json

from jrboard.install import (
    install_statusline,
    statusline_command,
    uninstall_statusline,
)


def test_command_uses_module_form_not_path() -> None:
    cmd = statusline_command(python_exe="/usr/bin/python3", columns=80)
    # '-m jrboard' keeps it working without PATH / repo clone.
    assert "-m jrboard" in cmd
    assert "--mode statusline" in cmd
    assert "--claude-stdin" in cmd
    assert "--columns 80" in cmd


def test_command_by_session_default_when_no_line() -> None:
    cmd = statusline_command(python_exe="python3")
    assert "--by-session" in cmd
    assert "--tokens" in cmd


def test_command_explicit_line_drops_by_session() -> None:
    cmd = statusline_command(python_exe="python3", line="oedo", station="tochomae")
    assert "--by-session" not in cmd      # an explicit line wins
    assert "--line oedo" in cmd
    assert "--station tochomae" in cmd


def test_command_minitable_and_city() -> None:
    cmd = statusline_command(python_exe="python3", minitable=True, city="Osaka")
    assert "--mode minitable" in cmd
    assert "--city Osaka" in cmd


def test_command_quotes_spaced_python_path() -> None:
    cmd = statusline_command(python_exe="/opt/my python/bin/python3")
    assert "'/opt/my python/bin/python3'" in cmd  # shlex-quoted


def test_install_creates_and_merges(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "opus", "language": "en"}), encoding="utf-8")
    ok, msg = install_statusline("python3 -m jrboard ...", settings_path=str(path))
    assert ok, msg
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["statusLine"]["command"] == "python3 -m jrboard ..."
    assert data["statusLine"]["type"] == "command"
    assert data["statusLine"]["refreshInterval"] == 1
    # Existing keys are preserved (merge, not overwrite).
    assert data["model"] == "opus"
    assert data["language"] == "en"
    # A backup of the prior file was written.
    assert (tmp_path / "settings.json.jrboard.bak").exists()


def test_install_into_missing_file(tmp_path) -> None:
    path = tmp_path / "sub" / "settings.json"  # parent dir does not exist yet
    ok, _ = install_statusline("cmd", settings_path=str(path))
    assert ok
    assert json.loads(path.read_text())["statusLine"]["command"] == "cmd"


def test_uninstall_removes_only_statusline(tmp_path) -> None:
    path = tmp_path / "settings.json"
    install_statusline("cmd", settings_path=str(path))
    # add a sibling key, then uninstall
    data = json.loads(path.read_text()); data["keep"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    ok, _ = uninstall_statusline(settings_path=str(path))
    assert ok
    out = json.loads(path.read_text())
    assert "statusLine" not in out
    assert out["keep"] == 1


def test_uninstall_missing_file_is_ok(tmp_path) -> None:
    ok, _ = uninstall_statusline(settings_path=str(tmp_path / "nope.json"))
    assert ok
