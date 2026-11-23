"""Fetch ODPT ``StationTimetable`` JSON, cached on disk for a day.

Toei publishes its timetables on ODPT's public endpoint (CC BY 4.0, no key
needed); every other operator needs ``ODPT_KEY`` on the main endpoint.

Going online for Toei is opt-in: ``JRBOARD_LIVE=1``, or ``[live] enabled =
true`` in the config file (``JRBOARD_LIVE=0`` overrides the config). A
timetable only changes at a ダイヤ改正, so each query is fetched at most once a
day. A failed fetch is not retried for ``FAILURE_COOLDOWN_S``, because the
statusline starts a new process every second and must not hang on a dead
network.

Stdlib only (``urllib``), so the core package stays zero-dependency.
"""

from __future__ import annotations

import functools
import hashlib
import http.client
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__

PUBLIC_TIMETABLE_URL = "https://api-public.odpt.org/api/v4/odpt:StationTimetable"
KEYED_TIMETABLE_URL = "https://api.odpt.org/api/v4/odpt:StationTimetable"
CONSUMER_KEY_PARAM = "acl:consumerKey"
CACHE_TTL_S = 24 * 60 * 60
FAILURE_COOLDOWN_S = 10 * 60
TIMEOUT_S = 8

# Operators whose timetables are on the keyless public endpoint.
_PUBLIC_STATION_PREFIXES = ("odpt.Station:Toei.",)
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def live_enabled() -> bool:
    """True when the user opted in to fetching keyless timetables."""
    raw = os.environ.get("JRBOARD_LIVE")
    if raw is not None:
        return raw.strip().lower() in _TRUTHY
    return _config_live()


@functools.lru_cache(maxsize=1)
def _config_live() -> bool:
    from .config import load_config  # deferred: only needed when env is unset

    return load_config().live


def is_public(odpt_station: str) -> bool:
    """True for stations served by the keyless public endpoint (Toei)."""
    return odpt_station.startswith(_PUBLIC_STATION_PREFIXES)


def endpoint_for(
    odpt_station: str, key: str | None
) -> tuple[str, dict[str, str]]:
    """Return ``(url, auth_params)`` for ``odpt_station``; raise without a key."""
    if is_public(odpt_station):
        return PUBLIC_TIMETABLE_URL, {}
    if not key:
        raise RuntimeError(
            f"ODPT_KEY is required for {odpt_station or 'this station'}."
        )
    return KEYED_TIMETABLE_URL, {CONSUMER_KEY_PARAM: key}


def default_cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    return Path(base) / "jrboard" / "odpt"


def fetch_timetable(
    params: dict[str, str], key: str | None, *, cache_root: Path | None = None
) -> list:
    """Return the ODPT payload for ``params``, from cache when fresh.

    Raises ``RuntimeError`` when the key is missing, the request fails, the
    payload is empty, or a fetch failed within the cooldown. The cache file
    name is a hash of ``params`` only, so the key never reaches the disk.
    """
    url, auth = endpoint_for(params.get("odpt:station", ""), key)
    root = cache_root or default_cache_root()
    stem = hashlib.sha256(
        json.dumps(params, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    cached, failed = root / f"{stem}.json", root / f"{stem}.fail"

    if _age_s(cached) < CACHE_TTL_S:
        payload = _read_json(cached)
        if payload is not None:
            return payload
    if _age_s(failed) < FAILURE_COOLDOWN_S:
        raise RuntimeError("ODPT fetch failed recently; waiting out the cooldown.")

    query = urllib.parse.urlencode({**params, **auth})
    try:
        payload = _http_get_json(f"{url}?{query}")
    except (OSError, ValueError, http.client.HTTPException) as exc:
        _touch(failed)
        raise RuntimeError(f"ODPT request failed: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        _touch(failed)
        raise RuntimeError("ODPT returned an empty timetable.")

    _write_json(cached, payload)
    failed.unlink(missing_ok=True)
    return payload


def _http_get_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"jrboard/{__version__}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
        return json.load(resp)


def _age_s(path: Path) -> float:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return math.inf


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: list) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[jrboard] could not cache ODPT timetable: {exc}", file=sys.stderr)


def _touch(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError as exc:
        print(f"[jrboard] could not record ODPT failure: {exc}", file=sys.stderr)
