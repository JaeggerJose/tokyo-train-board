"""Domain model and JSON loading for railway lines.

Value objects are frozen dataclasses (immutable). Line data is read from the
JSON files under ``jrboard/data`` following the documented data contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

_DATA_SUBDIR = "data"


@dataclass(frozen=True)
class Station:
    """A single station on a line."""

    id: str
    number: str
    name_jp: str
    kana: str
    name_en: str
    odpt_station: str


@dataclass(frozen=True)
class Direction:
    """A travel direction (e.g. inner/outer loop, or a terminus heading)."""

    id: str
    name_jp: str
    via_jp: str
    track: str


@dataclass(frozen=True)
class Line:
    """A railway line with its stations, color, and timetable metadata."""

    key: str
    name_jp: str
    name_en: str
    symbol: str
    operator: str
    odpt_railway: str
    loop: bool
    ansi_fg: str
    ansi_bg: str
    hex: str
    stations: tuple[Station, ...]
    first_train: str
    last_train: str
    headway_min: dict
    directions: tuple[Direction, ...]


def data_dir() -> str:
    """Return the absolute path to the ``jrboard/data`` directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, _DATA_SUBDIR)


def available_lines() -> list[str]:
    """Return the sorted keys (file basenames) of available line JSON files."""
    directory = data_dir()
    if not os.path.isdir(directory):
        return []
    keys: list[str] = []
    for name in os.listdir(directory):
        if name.endswith(".json") and not name.startswith("."):
            keys.append(name[: -len(".json")])
    return sorted(keys)


def _require(data: Mapping[str, Any], key: str, source: str) -> Any:
    """Return ``data[key]`` or raise a descriptive ``ValueError``."""
    if key not in data:
        raise ValueError(f"{source}: missing required field {key!r}")
    return data[key]


def _build_station(raw: Mapping[str, Any], source: str) -> Station:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: station entry must be an object")
    return Station(
        id=str(_require(raw, "id", source)),
        number=str(_require(raw, "number", source)),
        name_jp=str(_require(raw, "name_jp", source)),
        kana=str(_require(raw, "kana", source)),
        name_en=str(_require(raw, "name_en", source)),
        odpt_station=str(_require(raw, "odpt_station", source)),
    )


def _build_direction(raw: Mapping[str, Any], source: str) -> Direction:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: direction entry must be an object")
    return Direction(
        id=str(_require(raw, "id", source)),
        name_jp=str(_require(raw, "name_jp", source)),
        via_jp=str(_require(raw, "via_jp", source)),
        track=str(_require(raw, "track", source)),
    )


def _build_line(data: Mapping[str, Any], source: str) -> Line:
    if not isinstance(data, Mapping):
        raise ValueError(f"{source}: top-level JSON must be an object")

    color = _require(data, "color", source)
    if not isinstance(color, Mapping):
        raise ValueError(f"{source}: 'color' must be an object")

    timetable = _require(data, "timetable", source)
    if not isinstance(timetable, Mapping):
        raise ValueError(f"{source}: 'timetable' must be an object")

    raw_stations = _require(data, "stations", source)
    if not isinstance(raw_stations, list) or not raw_stations:
        raise ValueError(f"{source}: 'stations' must be a non-empty array")

    raw_directions = _require(timetable, "directions", source)
    if not isinstance(raw_directions, list) or not raw_directions:
        raise ValueError(f"{source}: 'directions' must be a non-empty array")

    headway = _require(timetable, "headway_min", source)
    if not isinstance(headway, Mapping):
        raise ValueError(f"{source}: 'headway_min' must be an object")

    stations = tuple(_build_station(s, source) for s in raw_stations)
    directions = tuple(_build_direction(d, source) for d in raw_directions)

    return Line(
        key=str(_require(data, "key", source)),
        name_jp=str(_require(data, "name_jp", source)),
        name_en=str(_require(data, "name_en", source)),
        symbol=str(_require(data, "symbol", source)),
        operator=str(_require(data, "operator", source)),
        odpt_railway=str(_require(data, "odpt_railway", source)),
        loop=bool(_require(data, "loop", source)),
        ansi_fg=str(_require(color, "ansi_fg", source)),
        ansi_bg=str(_require(color, "ansi_bg", source)),
        hex=str(_require(color, "hex", source)),
        stations=stations,
        first_train=str(_require(timetable, "first_train", source)),
        last_train=str(_require(timetable, "last_train", source)),
        headway_min=dict(headway),
        directions=directions,
    )


def load_line(key: str) -> Line:
    """Load and parse the line identified by ``key``.

    Raises ``ValueError`` if the key is unknown (with the list of available
    keys) or if the JSON file is malformed.
    """
    if not isinstance(key, str) or not key:
        raise ValueError("line key must be a non-empty string")

    normalized = key.strip().lower()
    available = available_lines()
    if normalized not in available:
        listed = ", ".join(available) if available else "(none found)"
        raise ValueError(
            f"unknown line {key!r}; available lines: {listed}"
        )

    path = os.path.join(data_dir(), f"{normalized}.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ValueError(f"cannot read line file {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path!r}: {exc}") from exc

    return _build_line(data, source=os.path.basename(path))


def find_station(line: Line, station_key: str) -> Station:
    """Find a station on ``line`` by name_en, id, or number.

    Matching is case-insensitive and whitespace-trimmed. Raises ``ValueError``
    if no station matches.
    """
    if not isinstance(line, Line):
        raise TypeError("line must be a Line instance")
    if not isinstance(station_key, str) or not station_key.strip():
        raise ValueError("station_key must be a non-empty string")

    needle = station_key.strip().lower()
    for station in line.stations:
        candidates = (
            station.name_en.lower(),
            station.id.lower(),
            station.number.lower(),
            station.number.lstrip("0").lower(),
        )
        if needle in candidates:
            return station

    raise ValueError(
        f"no station matching {station_key!r} on line {line.key!r}"
    )


def neighbors(
    line: Line, station: Station
) -> tuple[Optional[Station], Station, Optional[Station]]:
    """Return ``(prev, curr, next)`` stations around ``station`` on ``line``.

    For loop lines the previous/next wrap around the ends. For non-loop lines
    the endpoints return ``None`` for the missing neighbor.
    """
    if not isinstance(line, Line):
        raise TypeError("line must be a Line instance")
    if not isinstance(station, Station):
        raise TypeError("station must be a Station instance")

    stations = line.stations
    try:
        index = next(
            i for i, s in enumerate(stations) if s.id == station.id
        )
    except StopIteration as exc:
        raise ValueError(
            f"station {station.id!r} is not on line {line.key!r}"
        ) from exc

    count = len(stations)
    if count == 1:
        return (None, station, None)

    if line.loop:
        prev_station: Optional[Station] = stations[(index - 1) % count]
        next_station: Optional[Station] = stations[(index + 1) % count]
    else:
        prev_station = stations[index - 1] if index > 0 else None
        next_station = stations[index + 1] if index < count - 1 else None

    return (prev_station, station, next_station)
