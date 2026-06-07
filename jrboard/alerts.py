"""Local service-alert overlay.

Reads a JSON alerts file (e.g. ``~/.config/jrboard/alerts.json``) that any cron
job or scraper can write -- no hard ODPT dependency -- and stamps matching
departures with ``delay_min`` / ``alert_text`` so the board can badge them
``[+N分]`` / ``⚠`` and footer the cause. This is the substrate a future live
ODPT layer would write into.

Pure and stdlib-only: a missing or malformed file yields no overlay and never
raises; stamping returns NEW :class:`Departure` objects (the input is never
mutated).

Alert file format (a JSON list)::

    [{"line": "yamanote", "station": "shinjuku",
      "times": ["21:52"], "delay_min": 2, "reason": "人身事故"}]

``line``/``station``/``times`` are all optional filters: an absent ``line`` or
``station`` matches any; absent/empty ``times`` matches every departure.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Optional

from .sources import Departure

__all__ = ["load_alerts", "apply_alerts"]


def load_alerts(path: str) -> list[dict]:
    """Load the alerts list from ``path``; ``[]`` on any problem. Never raises."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [a for a in data if isinstance(a, dict)]


def _matches(alert: dict, dep: Departure, line_key: str, station_key: str) -> bool:
    line = alert.get("line")
    if line and str(line).lower() != str(line_key).lower():
        return False
    station = alert.get("station")
    if station and str(station).lower() != str(station_key).lower():
        return False
    times = alert.get("times")
    if isinstance(times, list) and times:
        return dep.time in {str(t) for t in times}
    return True  # absent/empty times => whole line/station


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_alerts(
    departures: list[Departure],
    alerts: list[dict],
    line_key: str,
    station_key: str,
) -> list[Departure]:
    """Return ``departures`` with matching alerts stamped on (immutably)."""
    if not alerts:
        return list(departures)
    out: list[Departure] = []
    for dep in departures:
        delay = dep.delay_min
        text = dep.alert_text
        for alert in alerts:
            if not _matches(alert, dep, line_key, station_key):
                continue
            d = _int_or_none(alert.get("delay_min"))
            if d is not None:
                delay = d
            reason = alert.get("reason")
            if isinstance(reason, str) and reason.strip():
                text = reason.strip()
        if delay is dep.delay_min and text is dep.alert_text:
            out.append(dep)
        else:
            out.append(dataclasses.replace(dep, delay_min=delay, alert_text=text))
    return out
