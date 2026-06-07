"""Offline JSONL departure cache.

Persists each successful departure fetch as one timestamped JSONL line so the
board can replay the most recent snapshot when the live source is unavailable --
the "never goes blank on flaky train wifi" promise. Pure stdlib; the caller
supplies ``now_epoch`` so this stays clock-free and fully testable. Every
operation is defensive: a cache miss / unreadable file yields ``None`` and never
raises.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Optional

from .sources import Departure

__all__ = ["cache_path", "write_snapshot", "read_latest"]


def _safe_key(text: str) -> str:
    """Filesystem-safe slug for a line/station key."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(text))


def cache_path(cache_dir: str, line_key: str, station_key: str) -> str:
    """Per line+station JSONL cache file path."""
    return os.path.join(cache_dir, f"{_safe_key(line_key)}__{_safe_key(station_key)}.jsonl")


def write_snapshot(
    cache_dir: str,
    line_key: str,
    station_key: str,
    departures: list[Departure],
    now_epoch: float,
) -> bool:
    """Append a timestamped snapshot line. Returns ``True`` on success."""
    try:
        os.makedirs(cache_dir, exist_ok=True)
        record = {
            "ts": int(now_epoch),
            "deps": [dataclasses.asdict(d) for d in departures],
        }
        with open(cache_path(cache_dir, line_key, station_key), "a",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_latest(
    cache_dir: str,
    line_key: str,
    station_key: str,
    now_epoch: float,
    max_age_sec: int,
) -> Optional[tuple[list[Departure], int]]:
    """Return ``(departures, age_minutes)`` from the freshest snapshot, or ``None``.

    ``None`` when there is no cache, it is unreadable, or the newest snapshot is
    older than ``max_age_sec``.
    """
    path = cache_path(cache_dir, line_key, station_key)
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        return None
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
        ts = int(record["ts"])
        raw_deps = record["deps"]
    except (ValueError, KeyError, TypeError):
        return None

    age_sec = int(now_epoch) - ts
    if age_sec < 0 or age_sec > max_age_sec:
        return None

    deps: list[Departure] = []
    for d in raw_deps:
        if not isinstance(d, dict):
            continue
        try:
            deps.append(Departure(**d))
        except TypeError:
            # Tolerate schema drift: keep only the known fields.
            known = {k: d[k] for k in (
                "time", "kind_jp", "dest_jp", "track", "direction",
                "delay_min", "alert_text",
            ) if k in d}
            try:
                deps.append(Departure(**known))
            except TypeError:
                continue
    return deps, age_sec // 60
