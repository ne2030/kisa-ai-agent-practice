"""의도적 실패 2 — 결과 없는 tool로 인한 반복 호출.

버그: search_db가 항상 빈 결과를 반환하도록 override.
모델은 정보를 못 찾자 query를 바꿔가며 계속 재호출 시도.
max_steps 보호 장치가 트리거 → RuntimeError로 종료.

진단 포인트 (Langfuse trace에서):
1. 같은 tool을 몇 번 호출했는가
2. 호출마다 query가 다른지/같은지
3. 모델이 "no results" 응답을 받고도 계속 시도하는 이유
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


# 의도적 버그 — tool이 항상 빈 결과 반환
def _empty_search(query: str) -> str:
    return f"검색 완료: '{query}'에 대한 결과가 없습니다."


agent.HANDLERS["search_db"] = _empty_search


if __name__ == "__main__":
    print("=== infinite_loop_demo: tool이 빈 결과만 반환 ===\n")
    try:
        react_loop(
            "production 시스템에서 발생한 모든 에러 패턴을 찾아 정리해줘",
            max_steps=5,
        )
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        print("\n→ Langfuse trace 확인:")
        print("  • 같은 tool을 몇 번 호출했는가?")
        print("  • 매 호출마다 query가 어떻게 바뀌었는가?")
        print("  • 모델이 결과 없음을 받고도 계속 시도한 이유는?")
