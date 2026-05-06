"""의도적 실패 3 — Tool 결과는 비었는데 답은 자신만만 (hallucination).

버그: search_db가 빈 결과만 반환. 모델은 그럴듯한 답변을 만들어내거나,
무언가 추측해서 자신있게 답함.

진단 포인트 (Langfuse trace에서):
1. tool output (검색 결과 없음)
2. 최종 답변 (구체적인 정보로 채워져 있는가?)
3. 두 정보 사이의 grounding 단절 — 답변이 어디서 왔는지 추적 불가
4. 무엇이 더 위험한가: 솔직히 "모름"이라 말하는 모델 vs 그럴듯하게 만들어내는 모델

이 실습의 핵심: trace는 "왜 그런 답이 나왔는지" 추적할 수 있게 해주지만,
답변의 *진실성*까지 보장하지는 않음 → 다음 섹션 'Evaluation'으로 연결.

옵션 fix 방향:
- system prompt에 "데이터에 없는 것은 추측하지 말 것" 명시
- 답변에서 출처가 없는 주장을 자동 검증 (eval에서 다룸)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import agent
from agent import react_loop
from langfuse import get_client


# 의도적 버그 — tool은 항상 비어 있음
def _empty_search(query: str) -> str:
    return "검색 완료 — 매칭되는 데이터가 없습니다."


agent.HANDLERS["search_db"] = _empty_search


if __name__ == "__main__":
    print("=== hallucination_demo: 빈 데이터에 대해 모델이 어떻게 답하나? ===\n")

    # 매우 구체적인 질문 — tool 결과가 없어도 그럴듯하게 답할 가능성
    sample = (
        "사내 OAuth 시스템에서 user u999의 최근 로그인 패턴, "
        "사용 디바이스, 평균 세션 시간을 분석해서 알려줘. "
        "최대한 구체적으로."
    )

    try:
        answer = react_loop(sample, max_steps=4)

        print("\n=== 답변 ===")
        print(answer)
        print("\n→ Langfuse trace 확인:")
        print("  • search_db tool의 출력은 무엇이었는가?")
        print("  • 최종 답변에는 그 출력에 *없던* 정보가 있는가?")
        print("  • 답변의 각 주장이 어디에서 왔는지 추적 가능한가?")
    finally:
        get_client().flush()
