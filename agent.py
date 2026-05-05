"""Day 1 — ReAct loop 데모.

핵심 구조:
1. 도구(tool) 정의 — schema (LLM에게 알려주는 인터페이스) + 실제 함수
2. ReAct loop — observe → decide → act → observe 반복
3. stop 조건 — tool 호출이 더 없으면 최종 답변 반환

학생 작업 지점:
- TODO 1: 두 번째 tool 추가 (Step 2)
- TODO 2: @observe 데코레이터로 Langfuse trace 활성화 (Step 3)
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Step 3에서 사용할 Langfuse 데코레이터 (v3 SDK).
from langfuse import get_client, observe  # noqa: F401

load_dotenv()


# ============================================================
# 1) 도구 정의
# ============================================================

def search_db(query: str) -> str:
    """사내 DB 검색 (mock 구현)."""
    mock = {
        "production logs": (
            "최근 24시간: 5K logs · errors 0.2% · p95 latency 320ms"
        ),
        "error patterns": (
            "top: TimeoutError(45%), ConnectionRefused(28%), ValueError(12%)"
        ),
        "oauth": (
            "OAuth refresh token 만료된 user 12명 (user_id: u001~u012)"
        ),
    }
    for key, value in mock.items():
        if key in query.lower():
            return value
    return f"no results for: '{query}'"


# ------------------------------------------------------------
# TODO 1 — Step 2: 두 번째 tool을 추가하세요.
#
# 예시: get_user_info(user_id: str) -> str
#   1. 위 search_db 처럼 mock dict 기반 함수 정의
#   2. 아래 TOOLS 배열에 FunctionDeclaration 추가
#   3. HANDLERS dict에 함수 매핑 추가
# ------------------------------------------------------------


TOOLS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="search_db",
        description="사내 DB에서 키워드 검색",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="검색할 키워드 또는 자연어 표현",
                ),
            },
            required=["query"],
        ),
    ),
    # TODO 1 — 두 번째 tool의 FunctionDeclaration을 여기에
]

HANDLERS = {
    "search_db": search_db,
    # TODO 1 — 두 번째 tool의 함수 매핑을 여기에
}


# ============================================================
# 2) ReAct loop
# ============================================================

# ------------------------------------------------------------
# TODO 2 — Step 3: 아래 react_loop 함수에 @observe() 데코레이터를 붙이세요.
#
# 데코레이터를 붙이면 Langfuse가 자동으로 입출력 + 시간을 기록합니다.
# import는 파일 상단에 이미 준비돼 있습니다.
#
# 옵션: 데코레이터 안에서 trace metadata 추가
#   def react_loop(...):
#       get_client().update_current_trace(
#           user_id="your_nickname",
#           tags=["day1"],
#       )
#       ...
# ------------------------------------------------------------

# @observe()  ← TODO 2: 이 줄 주석 해제
def react_loop(user_input: str, max_steps: int = 10) -> str:
    """observe → decide → act → observe loop."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        )
    ]

    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=TOOLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    )

    for step in range(max_steps):
        print(f"\n[Step {step + 1}]")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )

        # 모델 응답에서 function_call과 text 부분 분리
        candidate = response.candidates[0]
        function_calls = []
        text_parts: list[str] = []
        for part in candidate.content.parts or []:
            if part.function_call:
                function_calls.append(part.function_call)
            elif part.text:
                text_parts.append(part.text)

        # tool 호출이 없으면 최종 답변
        if not function_calls:
            final = "\n".join(text_parts).strip()
            print(f"Final answer: {final[:200]}")
            return final

        # assistant turn (function_call 포함)을 history에 추가
        contents.append(candidate.content)

        # tool 실행 + 결과 추가
        for fc in function_calls:
            args = dict(fc.args) if fc.args else {}
            print(f"  → {fc.name}({args})")

            if fc.name not in HANDLERS:
                raise ValueError(f"Unknown tool: {fc.name}")

            result = HANDLERS[fc.name](**args)
            print(f"     ← {str(result)[:120]}")

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=fc.name,
                            response={"result": result},
                        )
                    ],
                )
            )

    raise RuntimeError(f"max_steps ({max_steps}) exceeded — no final answer")


# ============================================================
# 3) 실행
# ============================================================

if __name__ == "__main__":
    sample_query = "production logs를 분석해서 주요 에러 패턴을 알려줘"
    print(f"User: {sample_query}")
    answer = react_loop(sample_query)
    print("\n=== 최종 답변 ===")
    print(answer)
