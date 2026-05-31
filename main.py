#!/usr/bin/env python3
"""Thin entry point for the jrboard departure board.

Delegates everything to :func:`jrboard.cli.main` so the CLI logic stays in the
package and is independently testable.
"""

from __future__ import annotations

import sys

from jrboard.cli import main

if __name__ == "__main__":
    sys.exit(main())
