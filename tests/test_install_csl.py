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


# --- drift guard: every integrations theme must be bundled byte-identically -- #

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INTEGRATIONS = _REPO_ROOT / "integrations" / "csl"
_PACKAGE = _REPO_ROOT / "jrboard" / "csl"

# Discovered dynamically so a NEW theme dropped into integrations/csl is covered
# automatically (this is what jr-status slipped through before).
_INTEGRATION_THEME_FILES = sorted(
    p.name for p in _INTEGRATIONS.glob("*.sh")
) + sorted(p.name for p in _INTEGRATIONS.glob("*.json"))


@pytest.mark.parametrize("name", _INTEGRATION_THEME_FILES)
def test_package_theme_matches_integrations_copy(name: str) -> None:
    """jrboard/csl/<f> and integrations/csl/<f> must be byte-identical.

    Prevents the stale/missing-theme drift bug (a theme in integrations/csl that
    is not bundled, or a bundled copy diverging from the canonical source) from
    ever recurring. Parametrized over whatever themes exist in integrations/csl.
    """
    bundled = _PACKAGE / name
    assert bundled.exists(), (
        f"{name} exists in integrations/csl but is NOT bundled in jrboard/csl "
        f"(so 'jrboard install-csl-theme' cannot ship it)"
    )
    assert bundled.read_bytes() == (_INTEGRATIONS / name).read_bytes(), (
        f"{name} drifted between jrboard/csl and integrations/csl"
    )


def test_no_bundled_theme_hardcodes_an_absolute_home() -> None:
    """Bundled themes must stay portable -- no author-specific absolute paths."""
    for path in list(_PACKAGE.glob("*.sh")) + list(_PACKAGE.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text and "/home/" not in text, (
            f"{path.name} hardcodes an absolute home path -- not portable"
        )


def test_every_bundled_theme_is_installable(tmp_path) -> None:
    """install_csl_theme must succeed for every theme available()."""
    for theme in available_csl_themes():
        ok, msg = install_csl_theme(theme, dest_dir=str(tmp_path / theme))
        assert ok, msg
