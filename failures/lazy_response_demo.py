"""의도적 실패 4 — system_instruction 부재로 인한 "punt".

버그: SYSTEM_INSTRUCTION을 비워서 모델이 tool 결과를 받고도
"확인하겠습니다 / 분석하겠습니다" 같은 *예의성 중간 응답*으로 turn을
종료해버림. tool 호출까지는 잘 되는데 정작 분석은 안 함.

진단 포인트 (Langfuse trace에서):
  1. tool 호출은 정상적으로 일어났는가? (대부분 yes — 데이터까지 받음)
  2. 마지막 step의 응답이 *실제 분석*인가, *예의성 마무리*인가?
  3. system prompt가 없을 때 LLM은 왜 이렇게 행동하는가?
     → 학습된 default behavior. "안전하게" 인사하고 다음 turn에 답하려는 패턴
  4. production agent에서 이 문제가 반복되면 어떤 영향이 있는가?

이 실습의 핵심: prompt engineering은 *마법*이 아니라
**failure mode를 하나씩 봉쇄하는 작업**이다. system_instruction은
그 가장 첫 번째 방어선.

옵션 fix:
- agent.SYSTEM_INSTRUCTION을 비우는 줄을 제거하면 baseline 동작 복원
- 또는 system_instruction에 "tool 결과를 받으면 즉시 답변하라"고 명시
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import agent
from agent import react_loop
from langfuse import get_client


# 의도적 버그 — system_instruction을 비움
agent.SYSTEM_INSTRUCTION = ""


if __name__ == "__main__":
    print("=== lazy_response_demo: system_instruction 부재 ===\n")

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
        get_client().flush()
