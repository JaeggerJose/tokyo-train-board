"""Departure data sources for jrboard (repository pattern).

Two interchangeable timetable sources sit behind the ``TimetableSource``
protocol: ``ODPTSource`` (live ODPT v4 ``StationTimetable``) and
``StaticSource`` (offline generator from ``Line.headway_min``).
``get_departures`` prefers ODPT when ``ODPT_KEY`` is set and falls back to
the static source (logging to ``stderr``) on any failure. ``requests`` is
imported lazily so the module is import-safe without it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol

from jrboard.model import Direction, Line, Station

__all__ = [
    "Departure",
    "TimetableSource",
    "ODPTSource",
    "StaticSource",
    "get_departures",
]

# ODPT v4 facts (confirmed).
ODPT_STATION_TIMETABLE = "https://api.odpt.org/api/v4/odpt:StationTimetable"
ODPT_CONSUMER_KEY_PARAM = "acl:consumerKey"
_HTTP_TIMEOUT_S = 8

# Default train kind (種別) when none is supplied by the source.
DEFAULT_KIND_JP = "各駅停車"

# Minimal map of common ODPT TrainType id suffixes -> Japanese label.
_TRAIN_TYPE_JP: dict[str, str] = {
    "Local": "各駅停車",
    "Rapid": "快速",
    "CommuterRapid": "通勤快速",
    "SpecialRapid": "特別快速",
    "Express": "急行",
    "CommuterExpress": "通勤急行",
    "LimitedExpress": "特急",
    "SemiExpress": "準急",
    "AccessExpress": "アクセス特急",
    "AirportRapidLimitedExpress": "エアポート快特",
    "RapidLimitedExpress": "快特",
}


@dataclass(frozen=True)
class Departure:
    """One departure: time HH:MM, 種別, 行先/方面, 番線, direction id."""

    time: str
    kind_jp: str
    dest_jp: str
    track: str
    direction: str


class TimetableSource(Protocol):
    """Repository protocol for departure providers."""

    def departures(
        self, line: Line, station: Station, now: datetime, limit: int
    ) -> list[Departure]:
        """Return up to ``limit`` upcoming departures for ``station``."""
        ...


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    """Parse ``"HH:MM"`` into ``(hour, minute)`` or ``None`` if malformed."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 47 and 0 <= minute <= 59):
        return None
    return hour, minute


def _minutes_since_midnight(now: datetime) -> int:
    return now.hour * 60 + now.minute


def _hhmm_to_minutes(value: str) -> int | None:
    """Minutes since midnight for an ``"HH:MM"`` string (wrap >24h)."""
    parsed = _parse_hhmm(value)
    if parsed is None:
        return None
    hour, minute = parsed
    return (hour % 24) * 60 + minute


def _format_hhmm(total_minutes: int) -> str:
    """Format minutes-since-midnight into ``"HH:MM"`` (wraps over 24h)."""
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _is_holiday(now: datetime) -> bool:
    """True for Saturday/Sunday (used to pick the headway schedule)."""
    return now.weekday() >= 5


def _station_phase(line: Line, station: Station) -> int:
    """Minutes a train lags the line origin by the time it reaches ``station``.

    Approximated as the station's 0-based position along the line (~1 min per
    hop). Used to shift the generated grid so each station shows DIFFERENT
    times — without it every station on a line would display an identical board.
    """
    for index, stn in enumerate(line.stations):
        if stn.id == station.id:
            return index
    return 0


class StaticSource:
    """Builds a believable departure list from ``Line.headway_min``.

    Lays down headway-spaced departures per direction from ``now`` forward,
    merges both directions, sorts by time, and truncates to ``limit``.
    """

    # Look-ahead window in minutes; wide enough for sparse late-night headways.
    _HORIZON_MIN = 5 * 60
    _GUARD_ITERATIONS = 512
    _DEFAULT_GAP = 5

    def departures(
        self, line: Line, station: Station, now: datetime, limit: int
    ) -> list[Departure]:
        if limit <= 0:
            return []

        directions = tuple(line.directions or ())
        if not directions:
            return []

        table = self._schedule_table(line, _is_holiday(now))
        now_min = _minutes_since_midnight(now)
        horizon_min = now_min + self._HORIZON_MIN

        # Per-station phase so adjacent stations show different times. A train
        # reaches station i ``phase`` minutes after the line origin, so the
        # arrivals visible at station i are the origin grid shifted by +phase.
        phase = _station_phase(line, station)

        candidates: list[Departure] = []
        for direction in directions:
            candidates.extend(
                self._direction_departures(
                    table, direction, now_min, horizon_min, phase
                )
            )

        candidates.sort(key=lambda dep: (_hhmm_to_minutes(dep.time) or 0))
        return candidates[:limit]

    @classmethod
    def _schedule_table(cls, line: Line, is_holiday: bool) -> dict:
        """Return the ``{hour: minutes}`` headway map for the day type.

        Tolerates the nested ``{"weekday":{}, "holiday":{}}`` and flat shapes.
        """
        headway = line.headway_min if isinstance(line.headway_min, dict) else {}
        table = headway.get("holiday" if is_holiday else "weekday")
        if isinstance(table, dict):
            return table
        return headway

    def _direction_departures(
        self,
        table: dict,
        direction: Direction,
        now_min: int,
        horizon_min: int,
        phase_min: int = 0,
    ) -> list[Departure]:
        # Generate in the line-origin "reference" window [now-phase, horizon-phase]
        # and display each slot shifted by +phase. This keeps displayed times in
        # [now, horizon] (future-only) while differing per station.
        out: list[Departure] = []
        ref_now = now_min - phase_min
        gap = self._gap_for_hour(table, (ref_now // 60) % 24)
        cursor = self._first_slot(ref_now, gap)

        for _ in range(self._GUARD_ITERATIONS):
            display = cursor + phase_min
            if display > horizon_min:
                break
            out.append(
                Departure(
                    time=_format_hhmm(display),
                    kind_jp=DEFAULT_KIND_JP,
                    dest_jp=direction.via_jp or direction.name_jp,
                    track=direction.track,
                    direction=direction.id,
                )
            )
            gap = self._gap_for_hour(table, (cursor // 60) % 24)
            cursor += gap
        return out

    @staticmethod
    def _first_slot(now_min: int, gap: int) -> int:
        """First headway-aligned slot at or after ``now_min``."""
        if gap <= 0:
            return now_min
        remainder = now_min % gap
        return now_min if remainder == 0 else now_min + (gap - remainder)

    @classmethod
    def _gap_for_hour(cls, table: dict, hour: int) -> int:
        """Headway in minutes for ``hour``; falls back to a sane default."""
        try:
            gap = int(table.get(str(hour)))
        except (TypeError, ValueError):
            return cls._DEFAULT_GAP
        return gap if gap > 0 else cls._DEFAULT_GAP


class ODPTSource:
    """Fetches departures from ODPT v4 ``StationTimetable`` using ``ODPT_KEY``.

    Raises on any failure (missing key, HTTP/network error, empty or
    unparseable payload) so ``get_departures`` can fall back to static data.
    """

    def departures(
        self, line: Line, station: Station, now: datetime, limit: int
    ) -> list[Departure]:
        key = os.environ.get("ODPT_KEY")
        if not key:
            raise RuntimeError("ODPT_KEY is not set in the environment.")

        try:
            import requests  # deferred so the module imports without it
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("requests is required for ODPTSource.") from exc

        params = {
            ODPT_CONSUMER_KEY_PARAM: key,
            "odpt:station": station.odpt_station,
        }
        if line.odpt_railway:
            params["odpt:railway"] = line.odpt_railway
        params["odpt:calendar"] = (
            "odpt.Calendar:SaturdayHoliday"
            if _is_holiday(now)
            else "odpt.Calendar:Weekday"
        )

        try:
            resp = requests.get(
                ODPT_STATION_TIMETABLE,
                params=params,
                timeout=_HTTP_TIMEOUT_S,
            )
        except Exception as exc:  # network errors, DNS, TLS, etc.
            raise RuntimeError(f"ODPT request failed: {exc}") from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"ODPT returned HTTP {resp.status_code}: "
                f"{resp.text[:120]!r}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise RuntimeError("ODPT returned non-JSON payload.") from exc

        if not isinstance(payload, list) or not payload:
            raise RuntimeError("ODPT returned an empty timetable.")

        entries = self._collect_entries(payload)
        if not entries:
            raise RuntimeError("ODPT timetable contained no departures.")

        departures = self._to_departures(line, entries, now)
        if not departures:
            raise RuntimeError("No upcoming ODPT departures after now.")

        departures.sort(key=lambda dep: (_hhmm_to_minutes(dep.time) or 0))
        return departures[: max(limit, 0)]

    @staticmethod
    def _collect_entries(payload: list) -> list[dict]:
        """Flatten ``odpt:stationTimetableObject`` arrays across tables."""
        entries: list[dict] = []
        for table in payload:
            if not isinstance(table, dict):
                continue
            objects = table.get("odpt:stationTimetableObject")
            if isinstance(objects, list):
                rail_dir = table.get("odpt:railDirection")
                for obj in objects:
                    if isinstance(obj, dict):
                        merged = dict(obj)
                        merged.setdefault("_railDirection", rail_dir)
                        entries.append(merged)
        return entries

    def _to_departures(
        self, line: Line, entries: Iterable[dict], now: datetime
    ) -> list[Departure]:
        now_min = _minutes_since_midnight(now)
        out: list[Departure] = []
        for obj in entries:
            dep_time = obj.get("odpt:departureTime")
            slot = _hhmm_to_minutes(dep_time) if isinstance(dep_time, str) else None
            if slot is None or slot < now_min:
                continue
            out.append(
                Departure(
                    time=dep_time,
                    kind_jp=self._kind_jp(obj.get("odpt:trainType")),
                    dest_jp=self._dest_jp(line, obj),
                    track=self._track(obj),
                    direction=self._direction_id(line, obj),
                )
            )
        return out

    @staticmethod
    def _kind_jp(train_type: object) -> str:
        if not isinstance(train_type, str) or not train_type:
            return DEFAULT_KIND_JP
        suffix = train_type.rsplit(".", 1)[-1]
        return _TRAIN_TYPE_JP.get(suffix, DEFAULT_KIND_JP)

    @staticmethod
    def _dest_jp(line: Line, obj: dict) -> str:
        dests = obj.get("odpt:destinationStation")
        station_id = ""
        if isinstance(dests, list) and dests:
            station_id = str(dests[0])
        elif isinstance(dests, str):
            station_id = dests
        if station_id:
            matched = ODPTSource._station_jp(line, station_id)
            if matched:
                return f"{matched}方面"
            suffix = station_id.rsplit(".", 1)[-1]
            if suffix:
                return f"{suffix}方面"
        return "方面不明"

    @staticmethod
    def _station_jp(line: Line, odpt_station_id: str) -> str:
        for st in line.stations:
            if st.odpt_station == odpt_station_id:
                return st.name_jp
        return ""

    @staticmethod
    def _track(obj: dict) -> str:
        platform = obj.get("odpt:platformNumber")
        if platform is not None:
            return str(platform)
        return ""

    @staticmethod
    def _direction_id(line: Line, obj: dict) -> str:
        rail_dir = obj.get("_railDirection")
        if isinstance(rail_dir, str) and rail_dir:
            suffix = rail_dir.rsplit(".", 1)[-1].lower()
            # Match exact id first, then containment (e.g. "InnerLoop"~"inner").
            for direction in line.directions:
                if direction.id.lower() == suffix:
                    return direction.id
            for direction in line.directions:
                did = direction.id.lower()
                if did and (did in suffix or suffix in did):
                    return direction.id
            return suffix
        if line.directions:
            return line.directions[0].id
        return ""


def get_departures(
    line: Line,
    station: Station,
    now: datetime,
    limit: int = 6,
) -> tuple[list[Departure], str]:
    """Return ``(departures, label)`` where label is ``"ODPT"`` or ``"STATIC"``.

    Tries :class:`ODPTSource` only when ``ODPT_KEY`` is present; on any
    failure it logs to ``stderr`` and falls back to :class:`StaticSource`.
    """
    if os.environ.get("ODPT_KEY"):
        try:
            departures = ODPTSource().departures(line, station, now, limit)
            return departures, "ODPT"
        except Exception as exc:
            print(
                f"[jrboard] ODPT source failed, using static data: {exc}",
                file=sys.stderr,
            )

    return StaticSource().departures(line, station, now, limit), "STATIC"
