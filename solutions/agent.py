"""Day 1 — agent.py 정답 (TODO 1, 2 완성).

학생이 막혔을 때 비교용. 강의자가 적절한 시점에 공개.
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langfuse.decorators import langfuse_context, observe

load_dotenv()


# ============================================================
# 1) 도구 정의
# ============================================================

def search_db(query: str) -> str:
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


# === TODO 1 정답 ===
def get_user_info(user_id: str) -> str:
    """user_id로 user 정보 조회 (mock)."""
    mock_users = {
        "u001": "name=Kim · team=Platform · role=Backend · joined=2024-03",
        "u002": "name=Lee · team=Data · role=Analyst · joined=2025-01",
        "u012": "name=Park · team=Platform · role=Frontend · joined=2025-08",
    }
    return mock_users.get(user_id, f"unknown user_id: '{user_id}'")


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
    # === TODO 1 정답 ===
    types.FunctionDeclaration(
        name="get_user_info",
        description="user_id로 사용자 정보 조회 (이름·팀·역할·입사일)",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "user_id": types.Schema(
                    type=types.Type.STRING,
                    description="조회할 사용자 ID, 예: 'u001'",
                ),
            },
            required=["user_id"],
        ),
    ),
]

HANDLERS = {
    "search_db": search_db,
    # === TODO 1 정답 ===
    "get_user_info": get_user_info,
}


# ============================================================
# 2) ReAct loop  (TODO 2 정답: @observe 활성화)
# ============================================================

@observe()  # ← TODO 2 정답
def react_loop(user_input: str, max_steps: int = 10) -> str:
    # 옵션: trace에 metadata 추가
    langfuse_context.update_current_trace(
        tags=["day1", "solution"],
    )

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

        candidate = response.candidates[0]
        function_calls = []
        text_parts: list[str] = []
        for part in candidate.content.parts or []:
            if part.function_call:
                function_calls.append(part.function_call)
            elif part.text:
                text_parts.append(part.text)

        if not function_calls:
            final = "\n".join(text_parts).strip()
            print(f"Final answer: {final[:200]}")
            return final

        contents.append(candidate.content)

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


if __name__ == "__main__":
    sample_query = "production logs와 OAuth refresh token 만료 user 정보를 종합해줘"
    print(f"User: {sample_query}")
    answer = react_loop(sample_query)
    print("\n=== 최종 답변 ===")
    print(answer)
