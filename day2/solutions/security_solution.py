"""2일차 보안 실습 참고 실행 파일.

기본값은 guarded 모드예요.
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
