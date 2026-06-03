"""Self-install jrboard as a Claude Code statusLine.

This is the "postinstall" that makes the project pip-install-and-go: after
``pip install tokyo-train-board`` a single ``jrboard install-statusline`` wires
the board into ``~/.claude/settings.json`` — no csl, no PATH fix, no repo clone.

The installed command uses ``<this-python> -m jrboard`` (via :data:`sys.executable`)
so it keeps working even when the ``jrboard`` console script is not on ``PATH``
(e.g. ``pip install --user`` -> ``~/.local/bin``).
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from importlib import resources
from typing import Optional

__all__ = [
    "default_settings_path",
    "statusline_command",
    "install_statusline",
    "uninstall_statusline",
    "available_csl_themes",
    "install_csl_theme",
]


def default_settings_path() -> str:
    """Path to Claude Code's user settings.json (honours ``CLAUDE_CONFIG_DIR``)."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
    return os.path.join(base, "settings.json")


def statusline_command(
    python_exe: Optional[str] = None,
    columns: int = 80,
    by_session: bool = True,
    tokens: bool = True,
    minitable: bool = False,
    line: Optional[str] = None,
    station: Optional[str] = None,
    city: Optional[str] = None,
    script: Optional[str] = None,
) -> str:
    """Build the shell command Claude Code should run for the statusLine.

    By default uses ``<python> -m jrboard`` so it is independent of ``PATH``
    (works after ``pip install --user``). When ``script`` is given (a path to a
    ``main.py`` from a git-clone install, where the package is NOT importable via
    ``-m``), uses ``<python> <script>`` instead -- ``main.py`` injects its own
    directory onto ``sys.path`` so it runs with no pip and no PATH. ``--by-session``
    is included only when no explicit ``line`` is pinned. Pure: returns a string.
    """
    exe = python_exe or sys.executable or "python3"
    runner = [shlex.quote(exe), shlex.quote(script)] if script else [
        shlex.quote(exe), "-m", "jrboard",
    ]
    parts = [
        *runner,
        "--mode", "minitable" if minitable else "statusline",
        "--claude-stdin",
    ]
    if tokens:
        parts.append("--tokens")
    if by_session and not line:
        parts.append("--by-session")
    if city:
        parts += ["--city", shlex.quote(city)]
    if line:
        parts += ["--line", shlex.quote(line)]
        if station:
            parts += ["--station", shlex.quote(station)]
    parts += ["--columns", str(int(columns))]
    return " ".join(parts)


def _load_settings(path: str) -> dict:
    """Load settings.json into a dict; return ``{}`` if absent/unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def install_statusline(
    command: str,
    settings_path: Optional[str] = None,
    refresh_interval: int = 1,
    padding: int = 0,
) -> tuple[bool, str]:
    """Merge a ``statusLine`` block into Claude Code settings.json.

    Backs up an existing settings.json to ``<path>.jrboard.bak`` before writing,
    and preserves every other key. Returns ``(ok, message)``; never raises.
    """
    path = settings_path or default_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        settings = _load_settings(path)
        had_existing = os.path.exists(path)
        if had_existing:
            backup = f"{path}.jrboard.bak"
            with open(backup, "w", encoding="utf-8") as fh:
                json.dump(settings, fh, ensure_ascii=False, indent=2)
        settings["statusLine"] = {
            "type": "command",
            "command": command,
            "padding": padding,
            "refreshInterval": refresh_interval,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        return False, f"could not write {path}: {exc}"
    note = " (previous settings backed up to settings.json.jrboard.bak)" if had_existing else ""
    return True, f"statusLine installed in {path}{note}"


def default_csl_themes_dir() -> str:
    """User-tier csl themes dir (honours ``CSL_USER_DIR``; default ~/.config/csl/themes)."""
    override = os.environ.get("CSL_USER_DIR")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".config", "csl", "themes")


def available_csl_themes() -> list[str]:
    """Names of csl themes bundled as package data (those having both .sh + .json)."""
    root = resources.files("jrboard.csl")
    names: set[str] = set()
    for entry in root.iterdir():
        name = entry.name
        if name.endswith(".sh") and root.joinpath(f"{name[:-3]}.json").is_file():
            names.add(name[:-3])
    return sorted(names)


def install_csl_theme(
    theme: str = "jr-board", dest_dir: Optional[str] = None
) -> tuple[bool, str]:
    """Copy a bundled csl theme (``<theme>.sh`` + ``<theme>.json``) into ``dest_dir``.

    ``dest_dir`` defaults to the user csl tier (``~/.config/csl/themes`` or
    ``CSL_USER_DIR``). ``theme`` must be one of :func:`available_csl_themes` --
    this both validates the name and blocks path traversal. Returns
    ``(ok, message)``; never raises.
    """
    valid = available_csl_themes()
    if theme not in valid:
        return False, (
            f"unknown csl theme {theme!r}; available: {', '.join(valid) or '(none)'}"
        )

    dest = dest_dir or default_csl_themes_dir()
    root = resources.files("jrboard.csl")
    try:
        os.makedirs(dest, exist_ok=True)
        written = []
        for ext in (".sh", ".json"):
            data = root.joinpath(f"{theme}{ext}").read_bytes()
            target = os.path.join(dest, f"{theme}{ext}")
            with open(target, "wb") as fh:
                fh.write(data)
            written.append(os.path.basename(target))
    except OSError as exc:
        return False, f"could not install theme into {dest}: {exc}"
    return True, (
        f"installed csl theme {theme!r} ({', '.join(written)}) into {dest} -- "
        f"activate with: csl set {theme}"
    )


def uninstall_statusline(settings_path: Optional[str] = None) -> tuple[bool, str]:
    """Remove the ``statusLine`` key from settings.json (leaves other keys)."""
    path = settings_path or default_settings_path()
    if not os.path.exists(path):
        return True, f"nothing to remove ({path} does not exist)"
    try:
        settings = _load_settings(path)
        if "statusLine" not in settings:
            return True, "no statusLine entry to remove"
        del settings["statusLine"]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        return False, f"could not write {path}: {exc}"
    return True, f"statusLine removed from {path}"
