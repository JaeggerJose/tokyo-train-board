"""Enable ``python3 -m jrboard`` as an entry point.

This matters for installs where the ``jrboard`` console script lands in a
directory that is not on ``PATH`` (e.g. ``pip install --user`` putting it in
``~/.local/bin``). ``python3 -m jrboard`` always works as long as the package
is importable, so the statusLine wiring and docs can rely on it.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
