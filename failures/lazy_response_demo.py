"""의도적 실패 4 — 잘못된 system_instruction으로 인한 "punt".

버그: SYSTEM_INSTRUCTION이 tool 결과를 분석하지 말고
"분석하겠습니다" 같은 *예의성 중간 응답*으로 끝내도록 유도.
tool 호출까지는 잘 되는데 정작 분석은 안 함.

진단 포인트 (Langfuse trace에서):
  1. tool 호출은 정상적으로 일어났는가? (대부분 yes — 데이터까지 받음)
  2. 마지막 step의 응답이 *실제 분석*인가, *예의성 마무리*인가?
  3. system prompt를 잘못 쓰면 LLM은 왜 이렇게 행동하는가?
     → 잘못된 instruction이 모델의 최종 행동을 제한
  4. production agent에서 이 문제가 반복되면 어떤 영향이 있는가?

이 실습의 핵심: prompt engineering은 *마법*이 아니라
**failure mode를 하나씩 봉쇄하는 작업**이다. system_instruction은
그 가장 첫 번째 방어선이지만, 잘못 쓰면 실패 모드 자체가 된다.

옵션 fix:
- 아래 잘못된 agent.SYSTEM_INSTRUCTION override를 제거하면 baseline 동작 복원
- 또는 system_instruction에 "tool 결과를 받으면 즉시 답변하라"고 명시
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import agent
from agent import react_loop
import langfuse


# 의도적 버그 — tool 결과를 받고도 실제 분석을 하지 않게 만드는 나쁜 prompt
agent.SYSTEM_INSTRUCTION = (
    "사용자의 요청에 필요한 tool을 호출하세요. "
    "단, tool 결과를 받은 뒤에는 실제 분석을 제공하지 말고 "
    "'분석하겠습니다'라고만 짧게 답하세요."
)


if __name__ == "__main__":
    print("=== lazy_response_demo: 잘못된 system_instruction ===\n")

    sample = "production logs를 분석해서 주요 에러 패턴을 알려줘"

    try:
        answer = react_loop(sample, max_steps=4)

        print("\n=== 답변 ===")
        print(answer)
        print("\n→ Langfuse trace 확인:")
        print("  • tool 호출은 정상이었는가? 그렇다면 답변이 빈약한 이유는?")
        print("  • 마지막 step 응답이 *분석*인가 *'분석하겠습니다'* 같은 punt인가?")
        print("  • system_instruction 한 줄이 어떻게 같은 모델을 다르게 동작시키는가?")
    finally:
        langfuse.get_client().flush()
