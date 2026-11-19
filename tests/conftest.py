"""Keep the suite offline no matter how the developer's shell is configured."""

from __future__ import annotations

import pytest

from jrboard import odpt_fetch


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("JRBOARD_LIVE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(odpt_fetch, "_config_live", lambda: False)
