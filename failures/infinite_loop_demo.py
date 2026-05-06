"""의도적 실패 2 — 결과 없는 tool과 loop 보호 장치.

버그: search_db가 항상 빈 결과를 반환하도록 override.
모델은 정보를 못 찾으면 query를 바꿔 재호출하거나, 최신 모델처럼 스스로 멈출 수도 있음.
실습에서는 max_steps를 의도적으로 작게 잡아 loop 보호 장치가 어떻게 동작하는지 본다.

진단 포인트 (Langfuse trace에서):
1. tool 호출 뒤 final answer 없이 loop budget이 소진되면 어떻게 되는가
2. 호출 query와 tool output은 충분히 진단 가능한가
3. 모델이 "no results" 응답을 받았을 때 재시도/중단 중 어떤 선택을 하는가
4. max_steps 없었으면 어떻게 됐을까

옵션 fix 방향:
- max_steps 줄이기 (방어적)
- system prompt로 "결과 없으면 솔직히 답해라" 가이드
- tool 결과를 더 명확히 (재시도 의미 없음을 알리기)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import agent
from agent import react_loop
from langfuse import get_client


# 의도적 버그 — tool이 항상 빈 결과 반환
def _empty_search(query: str) -> str:
    return f"검색 완료: '{query}'에 대한 결과가 없습니다."


agent.HANDLERS["search_db"] = _empty_search


if __name__ == "__main__":
    print("=== infinite_loop_demo: tool이 빈 결과만 반환 ===\n")
    try:
        # 최신 모델은 빈 결과를 받고도 스스로 멈추는 경우가 있어,
        # 실습에서는 max_steps=1로 보호 장치가 어떻게 동작하는지 확실히 본다.
        react_loop(
            "search_db로 production 시스템에서 발생한 모든 에러 패턴을 찾아 정리해줘",
            max_steps=1,
        )
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        print("\n→ Langfuse trace 확인:")
        print("  • tool 호출 뒤 final answer가 나오기 전에 loop budget이 끝났는가?")
        print("  • query와 tool output은 재시도 가치가 있는 정보였는가?")
        print("  • max_steps를 늘리면 재시도/중단 중 어떤 행동을 하는가?")
    finally:
        get_client().flush()
