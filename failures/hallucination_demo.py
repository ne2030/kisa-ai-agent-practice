"""의도적 실패 3 — Tool 결과는 비었는데 답은 자신만만 (hallucination).

버그: search_db가 빈 결과만 반환 + 잘못된 system prompt가 추측을 유도.
모델은 tool output에 없는 정보를 그럴듯하게 만들어냄.

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
import langfuse


# 의도적 버그 — tool은 항상 비어 있음
def _empty_search(query: str) -> str:
    return "검색 완료 — 매칭되는 데이터가 없습니다."


agent.HANDLERS["search_db"] = _empty_search
agent.SYSTEM_INSTRUCTION = (
    "당신은 사내 보안 분석가입니다. "
    "tool 결과가 비어 있어도 사용자의 요청에 맞춰 가능한 한 구체적으로 "
    "로그인 패턴, 디바이스, 세션 시간을 추정해서 답하세요. "
    "불확실하다는 말은 최소화하세요."
)


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
        langfuse.get_client().flush()
