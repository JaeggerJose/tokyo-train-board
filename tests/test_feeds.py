"""Tests for jrboard.feeds: .ics agenda parsing mapped onto Departure."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jrboard.feeds import departures_from_ics

_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART:20260531T090000
SUMMARY:Morning standup
END:VEVENT
BEGIN:VEVENT
DTSTART:20260531T140000Z
SUMMARY:Design review
END:VEVENT
BEGIN:VEVENT
DTSTART:20260531T173000
SUMMARY:Sprint planning
END:VEVENT
END:VCALENDAR
"""


def _write(tmp_path: Path, text: str) -> str:
    path = tmp_path / "agenda.ics"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_only_future_events_sorted_and_mapped(tmp_path: Path) -> None:
    """Past event dropped; future ones sorted, HH:MM, summary -> dest_jp."""
    ics = _write(tmp_path, _ICS)
    now = datetime(2026, 5, 31, 10, 0, 0)  # after 09:00, before 14:00

    deps = departures_from_ics(ics, now)

    assert [d.time for d in deps] == ["14:00", "17:30"]
    assert [d.dest_jp for d in deps] == ["Design review", "Sprint planning"]
    assert all(d.kind_jp == "予定" for d in deps)
    assert all(d.direction == "agenda" for d in deps)
    assert all(d.track == "" for d in deps)


def test_limit_truncates_results(tmp_path: Path) -> None:
    ics = _write(tmp_path, _ICS)
    now = datetime(2026, 5, 31, 0, 0, 0)

    deps = departures_from_ics(ics, now, limit=2)

    assert [d.time for d in deps] == ["09:00", "14:00"]


def test_events_on_other_days_excluded(tmp_path: Path) -> None:
    ics = _write(tmp_path, _ICS)
    now = datetime(2026, 6, 1, 0, 0, 0)  # next day

    assert departures_from_ics(ics, now) == []


def test_missing_file_returns_empty() -> None:
    assert departures_from_ics("/no/such/agenda.ics", datetime.now()) == []


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    """Garbage lines and a value-less event are tolerated."""
    text = (
        "BEGIN:VCALENDAR\n"
        "this is not a property line\n"
        "BEGIN:VEVENT\n"
        "SUMMARY:No start time\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "DTSTART:20260531T120000\n"
        "SUMMARY:Has start\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    ics = _write(tmp_path, text)
    now = datetime(2026, 5, 31, 8, 0, 0)

    deps = departures_from_ics(ics, now)

    assert [(d.time, d.dest_jp) for d in deps] == [("12:00", "Has start")]
