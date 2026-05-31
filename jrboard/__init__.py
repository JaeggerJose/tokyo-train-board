"""jrboard: a terminal split-flap (Solari) JR / Toei departure board.

The package is intentionally lightweight at import time. Heavy work (JSON
loading, network access, rendering) lives in submodules that callers import
explicitly:

- :mod:`jrboard.width`       visual width / ANSI-aware padding helpers
- :mod:`jrboard.model`       frozen value objects + JSON loading
- :mod:`jrboard.sources`     departure repositories (ODPT / static fallback)
- :mod:`jrboard.flap`        pure split-flap animation engine
- :mod:`jrboard.render`      ANSI board renderer
- :mod:`jrboard.statusline`  single-line marquee for Claude Code statusLine
- :mod:`jrboard.cli`         argparse entry point (``main``)
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
