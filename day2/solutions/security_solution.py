"""Reference runner for the Day 2 security lab.

Defaults to guarded mode so the reference run shows the solved state.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from day2.security_lab import main

if __name__ == "__main__":
    if "--mode" not in sys.argv:
        sys.argv.extend(["--mode", "guarded"])
    main()
