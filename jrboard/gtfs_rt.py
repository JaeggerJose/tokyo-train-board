"""GTFS-Realtime overlay source: stamp live delays + alerts onto departures.

This is an OVERLAY, not a timetable producer: it takes the departures the chain
already built (ODPT/STATIC) and stamps ``delay_min`` / ``alert_text`` from a
GTFS-Realtime feed's ``TripUpdate`` and ``Alert`` messages -- exactly mirroring
:mod:`jrboard.alerts`. The domain model has no per-trip stop_times join, so we
match at the ROUTE level (``line.odpt_railway``, or the ``GTFS_RT_ROUTE_ID``
override when the operator's GTFS route id differs).

The core stays zero-dependency: ``requests`` and ``gtfs-realtime-bindings``
(protobuf) are imported lazily inside the methods, so ``import jrboard.gtfs_rt``
works without the optional ``[gtfs]`` extra (the network/decode paths then raise
a clear "install ...[gtfs]" message, which the source chain catches).

Config (read from the environment at call time, mirroring ``ODPT_KEY``):
- ``GTFS_RT_URL``      -- feed endpoint returning protobuf bytes (the on-switch).
- ``GTFS_RT_ROUTE_ID`` -- optional route id override for matching.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only (PEP 563 strings) -> no runtime import cycle
    from .sources import Departure

__all__ = ["GtfsRtSource", "decode_feed"]

# Local copy of the HTTP timeout: importing it from sources at module top would
# create a sources<->gtfs_rt import cycle (sources imports GtfsRtSource at its
# bottom). Kept in sync with sources._HTTP_TIMEOUT_S by intent.
_HTTP_TIMEOUT_S = 8
_ALERT_MAXLEN = 60


def decode_feed(
    raw: bytes, now: datetime
) -> "tuple[dict[str, int], list[tuple[set[str], str]]]":
    """Decode GTFS-RT bytes into ``(route_id -> delay_min, [(routes, text)])``.

    Only currently-active alerts are returned (``active_period`` empty = always
    active). Delays are the max departure (fallback arrival) delay per route,
    floored at 0 and rounded to minutes; routes with no positive delay are
    omitted. Never raises: malformed/empty input yields ``({}, [])``.
    """
    try:
        from google.transit import gtfs_realtime_pb2  # lazy: optional [gtfs] extra
    except ImportError:
        return {}, []

    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(raw)
    except Exception:
        return {}, []

    now_epoch = now.timestamp()
    delays: dict[str, int] = {}
    alerts: list[tuple[set[str], str]] = []

    for entity in feed.entity:
        if entity.HasField("trip_update"):
            route = entity.trip_update.trip.route_id
            if route:
                worst = None
                for stu in entity.trip_update.stop_time_update:
                    d = None
                    if stu.HasField("departure") and stu.departure.delay:
                        d = stu.departure.delay
                    elif stu.HasField("arrival") and stu.arrival.delay:
                        d = stu.arrival.delay
                    if d is not None and (worst is None or d > worst):
                        worst = d
                if worst and worst > 0:
                    minutes = max(0, round(worst / 60))
                    if minutes > 0:
                        delays[route] = max(delays.get(route, 0), minutes)

        if entity.HasField("alert"):
            alert = entity.alert
            if not _alert_active(alert, now_epoch):
                continue
            text = _alert_text(alert)
            if not text:
                continue
            routes = {
                ie.route_id for ie in alert.informed_entity if ie.route_id
            }
            alerts.append((routes, text))

    return delays, alerts


def _alert_active(alert, now_epoch: float) -> bool:
    periods = alert.active_period
    if len(periods) == 0:
        return True
    for p in periods:
        start = p.start if p.start else None
        end = p.end if p.end else None
        if (start is None or start <= now_epoch) and (end is None or now_epoch <= end):
            return True
    return False


def _alert_text(alert) -> str:
    translations = alert.header_text.translation
    for t in translations:  # prefer Japanese
        if t.language == "ja" and t.text.strip():
            return t.text.strip()
    for t in translations:  # else first non-empty
        if t.text.strip():
            return t.text.strip()
    return ""


class GtfsRtSource:
    """Fetches a GTFS-RT feed and overlays delays/alerts onto departures."""

    def _fetch(self, url: str) -> bytes:
        """GET the feed; raise ``RuntimeError`` on a missing dep or HTTP error."""
        try:
            import requests  # lazy: optional [gtfs]/[live] extra
        except ImportError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "requests is required for GTFS-RT "
                "(pip install tokyo-train-board[gtfs])."
            ) from exc
        resp = requests.get(url, timeout=_HTTP_TIMEOUT_S)
        if resp.status_code != 200:
            raise RuntimeError(f"GTFS-RT returned HTTP {resp.status_code}")
        return resp.content

    def overlay(
        self,
        line,
        station,
        now: datetime,
        departures: list[Departure],
    ) -> list[Departure]:
        """Return ``departures`` with feed delays/alerts stamped (immutably).

        Matches the feed at the route level: ``GTFS_RT_ROUTE_ID`` env override,
        else ``line.odpt_railway``. Rows already carrying a value keep it when
        the feed is silent (same merge semantics as :mod:`jrboard.alerts`).
        """
        import dataclasses

        url = os.environ.get("GTFS_RT_URL")
        if not url:
            return list(departures)
        route_key = os.environ.get("GTFS_RT_ROUTE_ID") or getattr(
            line, "odpt_railway", ""
        )

        delays, alerts = decode_feed(self._fetch(url), now)

        delay = delays.get(route_key) if route_key else None
        texts = [t for routes, t in alerts if (not routes) or route_key in routes]
        combined = " / ".join(texts)[:_ALERT_MAXLEN] if texts else None

        if delay is None and combined is None:
            return list(departures)

        out: list[Departure] = []
        for dep in departures:
            new_delay = delay if delay is not None else dep.delay_min
            new_text = combined if combined is not None else dep.alert_text
            if new_delay == dep.delay_min and new_text == dep.alert_text:
                out.append(dep)
            else:
                out.append(
                    dataclasses.replace(dep, delay_min=new_delay, alert_text=new_text)
                )
        return out
