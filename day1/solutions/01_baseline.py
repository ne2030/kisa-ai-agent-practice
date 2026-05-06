"""Step 1 checkpoint — baseline ReAct loop.

아직 TODO를 풀지 않은 시작 상태입니다.

핵심 구조:
1. 도구(tool) 정의 — schema (LLM에게 알려주는 인터페이스) + 실제 함수
2. ReAct loop — observe → decide → act → observe 반복
3. stop 조건 — tool 호출이 더 없으면 최종 답변 반환

학생 작업 지점:
- TODO 1: 두 번째 tool 추가 (Step 2)
- TODO 2: @langfuse.observe 데코레이터로 Langfuse trace 활성화 (Step 3)
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Step 3에서 사용할 Langfuse 데코레이터.
import langfuse

load_dotenv()

MODEL_NAME = "gemini-2.5-flash"

# Gemini 2.5 Flash Standard paid-tier estimate (USD / 1M tokens).
# Token counts come from the Gemini response; cost is calculated locally so
# Langfuse can display a cost even if the model pricing is not configured there.
GEMINI_INPUT_USD_PER_1M = 0.30
GEMINI_OUTPUT_USD_PER_1M = 2.50


# system prompt — 모델의 동작 규약. 비워두거나 잘못 쓰면 모델이 tool 결과를
# 받고도 "확인하겠습니다 / 분석하겠습니다" 같은 punt로 끝낼 수 있음.
SYSTEM_INSTRUCTION = (
    "당신은 사내 데이터 분석 어시스턴트입니다. "
    "사용자의 질문을 받으면 필요한 tool을 호출해 데이터를 가져온 뒤, "
    "그 즉시 데이터를 사용해 분석한 결과를 답변하세요. "
    "'확인하겠습니다', '분석하겠습니다' 같은 중간 안내 멘트 없이 "
    "tool 결과를 받은 그 자리에서 바로 답변을 제공해야 합니다. "
    "tool 결과에 데이터가 없으면 확인된 데이터가 없다고 답하고, "
    "일반적인 패턴이나 추정 정보를 만들어내지 마세요. "
    "원인, 영향, 해결책도 tool 결과에 없으면 단정하지 마세요."
)


# ============================================================
# 1) 도구 정의
# ============================================================

def search_db(query: str) -> str:
    """사내 DB 검색 (mock 구현)."""
    normalized = query.lower()

    production_summary = "최근 24시간: 5K logs · errors 0.2% · p95 latency 320ms"
    error_patterns = "top errors: TimeoutError(45%), ConnectionRefused(28%), ValueError(12%)"
    oauth_summary = "OAuth refresh token 만료된 user 12명 (user_id: u001~u012)"

    wants_production = any(
        keyword in normalized
        for keyword in ["production", "prod", "logs", "로그", "상태", "latency"]
    )
    wants_errors = any(
        keyword in normalized
        for keyword in ["error", "errors", "에러", "오류", "패턴", "timeout", "connection"]
    )
    wants_oauth = any(
        keyword in normalized
        for keyword in ["oauth", "refresh", "token", "토큰", "만료"]
    )
    asks_unknown_user = any(
        keyword in normalized
        for keyword in ["u999", "존재하지", "로그인 이력", "login history"]
    )

    # Golden set이 자연어/한국어로 질문해도 안정적으로 같은 mock 데이터를 반환.
    if asks_unknown_user:
        return "확인된 데이터 없음: 해당 user의 로그인 이력이 없습니다."
    if wants_production and wants_errors:
        return f"{production_summary}\n{error_patterns}"
    if wants_errors:
        return error_patterns
    if wants_oauth:
        return oauth_summary
    if wants_production:
        return production_summary
    return f"확인된 데이터 없음: '{query}'"


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
# TODO 2 — Step 3: 아래 react_loop 함수에 @langfuse.observe() 데코레이터를 붙이세요.
#
# 데코레이터를 붙이면 Langfuse가 자동으로 입출력 + 시간을 기록합니다.
# import는 파일 상단에 이미 준비돼 있습니다.
#
# 옵션: 데코레이터 안에서 span metadata 추가
#   def react_loop(...):
#       langfuse.get_client().update_current_span(
#           metadata={"user_id": "your_nickname", "tags": ["day1"]},
#       )
#       ...
# ------------------------------------------------------------


def _last_text_preview(contents: list[types.Content]) -> str:
    """Langfuse span에 넣을 작은 입력 preview."""
    for content in reversed(contents):
        for part in reversed(content.parts or []):
            if part.text:
                return part.text[:200]
            if part.function_response:
                return str(part.function_response.response)[:200]
    return ""


def _response_preview(response) -> dict:
    """Gemini 응답에서 trace에 유용한 최소 정보만 추출."""
    candidate = response.candidates[0]
    tool_calls = []
    text_parts = []
    for part in candidate.content.parts or []:
        if part.function_call:
            tool_calls.append(
                {
                    "name": part.function_call.name,
                    "args": dict(part.function_call.args or {}),
                }
            )
        elif part.text:
            text_parts.append(part.text[:200])
    return {
        "tool_calls": tool_calls,
        "text_preview": "\n".join(text_parts)[:400],
    }


def _usage_details(response) -> dict[str, int]:
    """Gemini usage_metadata를 Langfuse usage_details 형식으로 변환."""
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return {}

    input_tokens = int(getattr(usage, "prompt_token_count", None) or 0)
    output_text_tokens = int(getattr(usage, "candidates_token_count", None) or 0)
    reasoning_tokens = int(getattr(usage, "thoughts_token_count", None) or 0)
    output_tokens = output_text_tokens + reasoning_tokens
    total_tokens = int(getattr(usage, "total_token_count", None) or 0)

    details = {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens or input_tokens + output_tokens,
    }

    # 아래 세부 항목은 디버깅용입니다. 과금 계산에는 input/output만 사용합니다.
    if output_text_tokens:
        details["candidates"] = output_text_tokens
    if reasoning_tokens:
        details["reasoning"] = reasoning_tokens

    cached_input_tokens = int(getattr(usage, "cached_content_token_count", None) or 0)
    if cached_input_tokens:
        details["cached_input"] = cached_input_tokens

    tool_use_prompt_tokens = int(getattr(usage, "tool_use_prompt_token_count", None) or 0)
    if tool_use_prompt_tokens:
        details["tool_use_prompt"] = tool_use_prompt_tokens

    return details


def _cost_details(usage_details: dict[str, int]) -> dict[str, float]:
    """Gemini 2.5 Flash Standard paid-tier 기준의 대략적 비용."""
    input_cost = usage_details.get("input", 0) * GEMINI_INPUT_USD_PER_1M / 1_000_000
    output_cost = usage_details.get("output", 0) * GEMINI_OUTPUT_USD_PER_1M / 1_000_000
    return {
        "input": input_cost,
        "output": output_cost,
        "total": input_cost + output_cost,
    }


# 관찰용 helper — Langfuse nested span을 예쁘게 보여주기 위한 코드입니다.
# 학생 실습에서는 이 블록을 수정하지 않아도 됩니다. TODO는 위의 tool 추가와
# 아래 react_loop의 parent @langfuse.observe 활성화 두 군데만 보면 됩니다.
@langfuse.observe(
    name="llm.generate_content",
    as_type="generation",
    capture_input=False,
    capture_output=False,
)
def call_llm(
    client: genai.Client,
    contents: list[types.Content],
    config: types.GenerateContentConfig,
    step: int,
):
    """LLM decide 단계. react_loop 아래 nested generation span으로 기록."""
    langfuse.get_client().update_current_generation(
        input={
            "step": step,
            "message_count": len(contents),
            "last_observation": _last_text_preview(contents),
        },
        metadata={
            "available_tools": [tool.name for tool in TOOLS],
            "pricing_note": "estimated Gemini 2.5 Flash Standard paid-tier USD",
        },
        model=MODEL_NAME,
    )
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=config,
    )
    usage_details = _usage_details(response)
    langfuse.get_client().update_current_generation(
        output=_response_preview(response),
        model=MODEL_NAME,
        usage_details=usage_details,
        cost_details=_cost_details(usage_details),
    )
    return response


@langfuse.observe(name="tool.execute", as_type="tool")
def execute_tool(tool_name: str, args: dict) -> str:
    """Host application의 tool validation + 실행을 nested tool span으로 기록."""
    if tool_name not in HANDLERS:
        raise ValueError(f"Unknown tool: {tool_name}")
    return HANDLERS[tool_name](**args)

# @langfuse.observe()  ← TODO 2: 이 줄 주석 해제
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
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[types.Tool(function_declarations=TOOLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=True,
        ),
    )

    for step in range(max_steps):
        print(f"\n[Step {step + 1}]")

        response = call_llm(client, contents, config, step + 1)

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

            result = execute_tool(fc.name, args)
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
    try:
        answer = react_loop(sample_query)
        print("\n=== 최종 답변 ===")
        print(answer)
    finally:
        langfuse.get_client().flush()
