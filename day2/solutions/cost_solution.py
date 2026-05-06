"""2일차 비용 실습 참고 실행 파일."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from day2.cost_lab import main

if __name__ == "__main__":
    main()
