"""의도적 실패 1 — Tool 이름 불일치.

버그: HANDLERS의 키와 TOOLS schema의 이름이 어긋나 있음.
모델은 schema에 등록된 'search_db'를 호출하지만, HANDLERS에는
오타로 'search_databse'만 있어 ValueError가 발생합니다.

진단 포인트 (Langfuse trace에서):
1. 마지막 step의 function_call name이 무엇인지
2. 우리 코드의 ValueError 메시지 vs HANDLERS의 실제 키
3. schema와 handler 사이의 contract가 어디서 깨졌는지

옵션 fix:
- HANDLERS 키 오타를 수정 → 다시 실행
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import agent
from agent import react_loop

# 의도적 버그 — search_db 핸들러를 오타 키로 등록
agent.HANDLERS["search_databse"] = agent.HANDLERS.pop("search_db")

if __name__ == "__main__":
    print("=== bad_tool_demo: HANDLERS 키 오타 ===\n")
    try:
        react_loop("production logs 분석")
    except Exception as e:
        print(f"\n❌ {type(e).__name__}: {e}")
        print("\n→ Langfuse trace 확인:")
        print("  • 모델이 호출한 function 이름은?")
        print("  • HANDLERS에는 어떤 키가 있는가?")
