"""Tests for the csl-theme installer (jrboard.install.install_csl_theme).

The goal of the feature: a pip-installed user can run
``jrboard install-csl-theme`` and get the portable csl theme dropped into
``~/.config/csl/themes/`` with NO manual ``cp`` and NO repo clone. The theme
files therefore ship as package data inside ``jrboard/csl/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jrboard.install import available_csl_themes, install_csl_theme


def test_lists_bundled_themes() -> None:
    themes = available_csl_themes()
    assert "jr-board" in themes
    assert "jr-timetable" in themes


def test_install_copies_sh_and_json(tmp_path) -> None:
    dest = tmp_path / "themes"
    ok, msg = install_csl_theme("jr-board", dest_dir=str(dest))
    assert ok, msg
    assert (dest / "jr-board.sh").exists()
    assert (dest / "jr-board.json").exists()
    # The shipped theme is the portable one (no hardcoded absolute home).
    sh = (dest / "jr-board.sh").read_text(encoding="utf-8")
    assert "/Users/minghsuan" not in sh
    assert "-m jrboard" in sh or "main.py" in sh


def test_install_creates_missing_dest(tmp_path) -> None:
    dest = tmp_path / "a" / "b" / "themes"  # nested, does not exist
    ok, _ = install_csl_theme("jr-board", dest_dir=str(dest))
    assert ok
    assert (dest / "jr-board.json").exists()


def test_unknown_theme_is_rejected(tmp_path) -> None:
    ok, msg = install_csl_theme("does-not-exist", dest_dir=str(tmp_path))
    assert not ok
    assert "does-not-exist" in msg


def test_theme_name_path_traversal_is_rejected(tmp_path) -> None:
    # A name with path separators must never escape the bundled-theme set.
    ok, _ = install_csl_theme("../../etc/passwd", dest_dir=str(tmp_path))
    assert not ok


def test_default_dest_honours_csl_user_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CSL_USER_DIR", str(tmp_path / "custom"))
    ok, msg = install_csl_theme("jr-timetable")
    assert ok, msg
    assert (tmp_path / "custom" / "jr-timetable.sh").exists()


# --- drift guard: package copy must equal the repo integrations copy -------- #

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "name", ["jr-board.sh", "jr-board.json", "jr-timetable.sh", "jr-timetable.json"]
)
def test_package_theme_matches_integrations_copy(name: str) -> None:
    """jrboard/csl/<f> and integrations/csl/<f> must be byte-identical.

    Prevents the stale-theme drift bug (the installed ~/.config copy diverging
    from the canonical portable source) from ever recurring at the repo level.
    """
    pkg = (_REPO_ROOT / "jrboard" / "csl" / name).read_bytes()
    repo = (_REPO_ROOT / "integrations" / "csl" / name).read_bytes()
    assert pkg == repo, f"{name} drifted between jrboard/csl and integrations/csl"
