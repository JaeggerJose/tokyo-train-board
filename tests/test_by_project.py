"""Per-project line selection (--by-project): one fixed line per Claude project."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from jrboard.claude_input import parse_claude_status, pick_by_project
from jrboard.model import available_lines, load_line

KEYS = ["yamanote", "ginza", "oedo", "chuo", "tozai", "hibiya"]


def _symbol_of(*extra: str, payload: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k != "COLUMNS"}
    proc = subprocess.run(
        [sys.executable, "-m", "jrboard", "--mode", "minitable",
         "--claude-stdin", "--no-color", *extra],
        input=json.dumps(payload), capture_output=True, text=True, env=env,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split("]")[0].lstrip("[")


def _payload(project: str, session: str = "s1") -> dict:
    return {"session_id": session,
            "workspace": {"project_dir": project, "current_dir": project + "/src"}}


def test_parse_project_dir_prefers_workspace_project_dir() -> None:
    status = parse_claude_status(json.dumps(_payload("/w/app")))
    assert status.project_dir == "/w/app"


def test_parse_project_dir_falls_back_to_cwd() -> None:
    status = parse_claude_status(json.dumps({"cwd": "/w/other"}))
    assert status.project_dir == "/w/other"


def test_pick_by_project_is_deterministic() -> None:
    assert pick_by_project(KEYS, "/w/app") == pick_by_project(KEYS, "/w/app")


def test_pick_by_project_ignores_trailing_slash() -> None:
    assert pick_by_project(KEYS, "/w/app/") == pick_by_project(KEYS, "/w/app")


def test_pick_by_project_distributes() -> None:
    assert len({pick_by_project(KEYS, f"/w/p{i}") for i in range(200)}) == len(KEYS)


def test_pick_by_project_empty_pool_raises() -> None:
    with pytest.raises(ValueError):
        pick_by_project([], "/w/app")


def test_pick_by_project_no_dir_is_first() -> None:
    assert pick_by_project(KEYS, "") == KEYS[0]


def test_cli_same_project_same_line_across_sessions() -> None:
    a = _symbol_of("--by-project", payload=_payload("/w/app", "s1"))
    b = _symbol_of("--by-project", payload=_payload("/w/app", "s2"))
    expected = load_line(pick_by_project(available_lines(), "/w/app")).symbol
    assert a == b == expected


def test_cli_by_project_beats_by_session() -> None:
    got = _symbol_of("--by-project", "--by-session", payload=_payload("/w/app", "s9"))
    assert got == load_line(pick_by_project(available_lines(), "/w/app")).symbol


def test_cli_explicit_line_beats_by_project() -> None:
    got = _symbol_of("--by-project", "--line", "oedo", payload=_payload("/w/app"))
    assert got == load_line("oedo").symbol
