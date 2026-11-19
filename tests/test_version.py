"""The package version must have exactly one source of truth.

``pyproject.toml`` reads it dynamically from ``jrboard.__version__`` so the two
can never drift apart again (they once said 0.4.0 vs 1.0.0).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import jrboard

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_pyproject_reads_version_from_package() -> None:
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    assert "version" not in project["project"], "version must not be hardcoded"
    assert "version" in project["project"]["dynamic"]
    dynamic = project["tool"]["setuptools"]["dynamic"]["version"]
    assert dynamic == {"attr": "jrboard.__version__"}


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", jrboard.__version__)
