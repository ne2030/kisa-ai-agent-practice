"""golden_set.yaml의 hard sample들을 react_loop에 돌려서 결과 평가.

체크 항목:
  1. must_call_tools — 기대한 tool들이 모두 호출됐는가
  2. must_mention   — 답변에 반드시 포함될 표현 존재 여부
  3. must_not_say   — 답변에 절대 나오면 안 되는 표현 존재 여부

옵션 stretch:
  - check() 함수를 더 엄격하게 만들거나, 점수 단위로 변경
  - LLM-as-Judge로 정성 평가 추가
"""

from pathlib import Path

import yaml

import agent
from agent import react_loop


# ----------------------------------------------------
# tool 호출 추적용 wrapper
# ----------------------------------------------------
def _wrap_handlers_for_tracking() -> list[str]:
    """HANDLERS의 각 함수를 wrap해서 호출 이름을 list에 누적."""
    called: list[str] = []
    for name, fn in list(agent.HANDLERS.items()):
        original = fn

        def make_wrapper(captured_name, captured_fn):
            def wrapper(*args, **kwargs):
                called.append(captured_name)
                return captured_fn(*args, **kwargs)
            return wrapper

        agent.HANDLERS[name] = make_wrapper(name, original)
    return called


def check(answer: str, tools_called: list[str], expected: dict) -> tuple[bool, list[str]]:
    """평가 결과 (passed, reasons) 반환."""
    reasons: list[str] = []

    # must_call_tools — set 비교
    expected_tools = set(expected.get("must_call_tools") or [])
    actual_tools = set(tools_called)
    if expected_tools - actual_tools:
        reasons.append(f"누락된 tool 호출: {sorted(expected_tools - actual_tools)}")
    if not expected_tools and actual_tools:
        reasons.append(f"불필요한 tool 호출: {sorted(actual_tools)}")

    # must_mention
    if not answer:
        reasons.append("답변이 비어있음")
    else:
        for phrase in expected.get("must_mention") or []:
            if phrase.lower() not in answer.lower():
                reasons.append(f"필수 표현 누락: '{phrase}'")
        for phrase in expected.get("must_not_say") or []:
            if phrase.lower() in answer.lower():
                reasons.append(f"금지 표현 등장: '{phrase}'")

    return (not reasons), reasons


def evaluate_one(case: dict) -> dict:
    tracked = _wrap_handlers_for_tracking()
    try:
        answer = react_loop(case["input"], max_steps=5)
        passed, reasons = check(answer, tracked, case["expected"])
        return {
            "id": case["id"],
            "passed": passed,
            "answer": answer,
            "tools": list(tracked),
            "reasons": reasons,
        }
    except Exception as e:
        return {
            "id": case["id"],
            "passed": False,
            "answer": None,
            "tools": list(tracked),
            "reasons": [f"실행 에러: {type(e).__name__}: {e}"],
        }


if __name__ == "__main__":
    cases = yaml.safe_load(Path(__file__).parent.joinpath("golden_set.yaml").read_text(encoding="utf-8"))
    print(f"=== Evaluating {len(cases)} cases ===\n")

    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} — {case['input'][:60]}")
        result = evaluate_one(case)
        results.append(result)
        symbol = "✅" if result["passed"] else "❌"
        print(f"  {symbol} tools={result['tools']}")
        if result["answer"]:
            print(f"     answer: {result['answer'][:100]}")
        if result["reasons"]:
            for r in result["reasons"]:
                print(f"     · {r}")
        print()

    passed_n = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"=== Summary: {passed_n}/{total} passed ({passed_n / total * 100:.0f}%) ===")
