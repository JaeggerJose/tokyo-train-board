"""User configuration and favorites for jrboard.

Configuration is read from ``~/.config/jrboard/config.toml`` (respecting
``XDG_CONFIG_HOME``) using the stdlib :mod:`tomllib` parser available on
Python 3.11+. The loader is intentionally defensive: a missing file, a
missing section/key, or a malformed value never raises -- it falls back to a
documented default and logs the reason to ``stderr``.

The configuration value object is a frozen dataclass; updates always produce
a new instance rather than mutating in place.
"""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass

__all__ = [
    "Config",
    "config_path",
    "load_config",
    "favorites_path",
    "load_favorites",
    "save_favorites",
]

_APP_DIR = "jrboard"
_CONFIG_FILENAME = "config.toml"
_FAVORITES_FILENAME = "favorites.txt"


@dataclass(frozen=True)
class Config:
    """Immutable user configuration with documented defaults.

    ``home`` / ``work`` are ``(line_key, station_key)`` pairs used by the
    commute guardian, or ``None`` when not configured.
    """

    line: str = "yamanote"
    station: str = "shinjuku"
    columns: int = 50
    width: int = 60
    flap_steps: int = 22
    flap_delay: float = 0.08
    pin_label: bool = True
    color: bool = True
    home: tuple[str, str] | None = None
    work: tuple[str, str] | None = None
    leave_buffer_min: int = 5


def _log(message: str) -> None:
    """Emit a namespaced advisory line to stderr (never raises)."""
    print(f"[jrboard] {message}", file=sys.stderr)


def _config_dir() -> str:
    """Return the jrboard config directory, honouring ``XDG_CONFIG_HOME``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, _APP_DIR)


def config_path() -> str:
    """Return the absolute path to ``config.toml``."""
    return os.path.join(_config_dir(), _CONFIG_FILENAME)


def favorites_path() -> str:
    """Return the absolute path to ``favorites.txt``."""
    return os.path.join(_config_dir(), _FAVORITES_FILENAME)


def _coerce_str(value: object, default: str) -> str:
    """Return ``value`` as a non-empty string, else ``default``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_int(value: object, default: int) -> int:
    """Return ``value`` coerced to ``int``, else ``default``."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_float(value: object, default: float) -> float:
    """Return ``value`` coerced to ``float``, else ``default``."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _coerce_bool(value: object, default: bool) -> bool:
    """Return ``value`` coerced to ``bool``, else ``default``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"true", "1", "yes", "on"}:
            return True
        if token in {"false", "0", "no", "off"}:
            return False
    return default


def _coerce_pair(value: object) -> tuple[str, str] | None:
    """Return a ``(line_key, station_key)`` pair from a 2-element array.

    Accepts a list/tuple of exactly two non-empty stringable items. Any other
    shape yields ``None`` so the caller treats it as unconfigured.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    first, second = value
    if not isinstance(first, str) or not isinstance(second, str):
        return None
    left = first.strip()
    right = second.strip()
    if not left or not right:
        return None
    return (left, right)


def _read_toml(path: str) -> dict:
    """Parse a TOML file into a dict; ``{}`` on any failure (logged)."""
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _log(f"could not read {path!r}: {exc}; using defaults")
        return {}
    except tomllib.TOMLDecodeError as exc:
        _log(f"malformed config {path!r}: {exc}; using defaults")
        return {}
    if not isinstance(data, dict):
        _log(f"config {path!r} is not a table; using defaults")
        return {}
    return data


def load_config() -> Config:
    """Load configuration from disk, returning defaults on any problem.

    Reads the ``[board]`` and ``[commute]`` tables. Every individual key is
    coerced to the expected type and falls back to its default if missing or
    malformed. This function never raises.
    """
    defaults = Config()
    data = _read_toml(config_path())
    if not data:
        return defaults

    board = data.get("board")
    if not isinstance(board, dict):
        board = {}
    commute = data.get("commute")
    if not isinstance(commute, dict):
        commute = {}

    return Config(
        line=_coerce_str(board.get("line"), defaults.line),
        station=_coerce_str(board.get("station"), defaults.station),
        columns=_coerce_int(board.get("columns"), defaults.columns),
        width=_coerce_int(board.get("width"), defaults.width),
        flap_steps=_coerce_int(board.get("flap_steps"), defaults.flap_steps),
        flap_delay=_coerce_float(board.get("flap_delay"), defaults.flap_delay),
        pin_label=_coerce_bool(board.get("pin_label"), defaults.pin_label),
        color=_coerce_bool(board.get("color"), defaults.color),
        home=_coerce_pair(commute.get("home")),
        work=_coerce_pair(commute.get("work")),
        leave_buffer_min=_coerce_int(
            commute.get("leave_buffer_min"), defaults.leave_buffer_min
        ),
    )


def load_favorites() -> list[tuple[str, str]]:
    """Load ``favorites.txt`` as a list of ``(line_key, station_key)`` pairs.

    Each non-empty, non-comment line must be ``"line_key,station_key"``.
    Malformed lines are skipped (logged). Returns ``[]`` if the file is
    missing or unreadable. This function never raises.
    """
    path = favorites_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw_lines = handle.readlines()
    except FileNotFoundError:
        return []
    except OSError as exc:
        _log(f"could not read favorites {path!r}: {exc}")
        return []

    favorites: list[tuple[str, str]] = []
    for index, raw in enumerate(raw_lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",")
        if len(parts) != 2:
            _log(f"favorites {path!r} line {index}: expected 'line,station'")
            continue
        line_key = parts[0].strip()
        station_key = parts[1].strip()
        if not line_key or not station_key:
            _log(f"favorites {path!r} line {index}: empty key")
            continue
        favorites.append((line_key, station_key))
    return favorites


def save_favorites(favs: list[tuple[str, str]]) -> None:
    """Write ``favorites.txt`` atomically, creating the config dir if needed.

    Each pair is serialised as ``"line_key,station_key"`` on its own line.
    The file is written to a temporary sibling and then atomically renamed so
    a crash mid-write never corrupts an existing favorites file.
    """
    directory = _config_dir()
    os.makedirs(directory, exist_ok=True)

    body = "".join(
        f"{line_key},{station_key}\n" for line_key, station_key in favs
    )

    path = favorites_path()
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
