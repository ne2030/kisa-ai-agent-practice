"""Reference runner for the Day 2 cost projection."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from day2.cost_projection import main

if __name__ == "__main__":
    main()
