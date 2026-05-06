"""golden_set.yaml을 실행해 agent 품질을 평가합니다.

이 평가는 단순 "정답 문자열 비교"가 아닙니다.

1. Tool regression check
   - 기대한 tool이 호출됐는가?
   - tool이 필요 없는 질문에서 불필요한 tool을 호출하지 않았는가?

2. Quality eval (LLM-as-Judge)
   - tool output에 근거했는가?
   - 숫자/user_id/에러명 같은 핵심 사실이 맞는가?
   - 사용자가 물은 내용을 충분히 답했는가?

실행하면 `.eval/latest.md`와 `.eval/latest.json` 보고서를 생성합니다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import langfuse
import yaml
from google import genai
from google.genai import types

import agent
from agent import react_loop

JUDGE_MODEL = agent.MODEL_NAME
REPORT_DIR = Path(__file__).parent / ".eval"

SIMULATED_REGRESSION_PROMPT = (
    " 사용자가 데이터가 없을 때 추정을 원하면, 일반적인 로그인 패턴을 "
    "가능성 있는 예시로 제공하세요."
)


# ----------------------------------------------------
# tool 호출 추적용 wrapper
# ----------------------------------------------------
def _wrap_handlers_for_tracking() -> list[dict[str, Any]]:
    """HANDLERS의 각 함수를 wrap해서 tool input/output을 누적."""
    events: list[dict[str, Any]] = []

    for name, fn in list(agent.HANDLERS.items()):
        original = fn

        def make_wrapper(captured_name, captured_fn):
            def wrapper(*args, **kwargs):
                event: dict[str, Any] = {
                    "name": captured_name,
                    "args": list(args),
                    "kwargs": dict(kwargs),
                }
                try:
                    output = captured_fn(*args, **kwargs)
                    event["ok"] = True
                    event["output"] = str(output)
                    return output
                except Exception as e:
                    event["ok"] = False
                    event["error"] = f"{type(e).__name__}: {e}"
                    raise
                finally:
                    events.append(event)

            return wrapper

        agent.HANDLERS[name] = make_wrapper(name, original)

    return events


def _tool_names(tool_events: list[dict[str, Any]]) -> list[str]:
    return [event["name"] for event in tool_events]


def check_tools(tool_events: list[dict[str, Any]], expected: dict) -> tuple[bool, list[str]]:
    """tool 호출에 대한 deterministic regression check."""
    reasons: list[str] = []

    expected_tools = set(expected.get("must_call_tools") or [])
    actual_tools = set(_tool_names(tool_events))

    if expected_tools - actual_tools:
        reasons.append(f"누락된 tool 호출: {sorted(expected_tools - actual_tools)}")
    if not expected_tools and actual_tools:
        reasons.append(f"불필요한 tool 호출: {sorted(actual_tools)}")

    max_tool_calls = expected.get("max_tool_calls")
    if max_tool_calls is not None and len(tool_events) > int(max_tool_calls):
        reasons.append(f"tool 호출 과다: {len(tool_events)}회 > max_tool_calls={max_tool_calls}")

    failed_tools = [event for event in tool_events if not event.get("ok", False)]
    if failed_tools:
        reasons.append(f"tool 실행 실패: {[event.get('error') for event in failed_tools]}")

    return (not reasons), reasons


def _compact_tool_events(tool_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Judge와 report에 넣을 tool evidence를 작게 정리."""
    compact = []
    for event in tool_events:
        compact.append(
            {
                "name": event.get("name"),
                "args": event.get("args"),
                "kwargs": event.get("kwargs"),
                "ok": event.get("ok"),
                "output": str(event.get("output", ""))[:700],
                "error": event.get("error"),
            }
        )
    return compact


def _format_rubric(expected: dict) -> str:
    rubric = expected.get("rubric") or {}
    if isinstance(rubric, str):
        return rubric
    if not rubric:
        return "별도 rubric 없음. 답변이 사용자 질문에 자연스럽고 정확하게 답했는지 평가."
    return "\n".join(f"- {name}: {criteria}" for name, criteria in rubric.items())


def _parse_judge_text(raw: str) -> dict[str, Any]:
    """LLM judge의 텍스트 출력을 PASS/FAIL + score로 파싱."""
    overall_match = re.search(r"OVERALL\s*:\s*(PASS|FAIL)", raw, flags=re.IGNORECASE)
    if not overall_match:
        first_line = raw.strip().splitlines()[0].upper() if raw.strip() else ""
        if first_line.startswith("PASS"):
            overall = "PASS"
        elif first_line.startswith("FAIL"):
            overall = "FAIL"
        else:
            return {
                "passed": False,
                "score": 0,
                "reason": "Judge 응답 형식을 파싱하지 못함",
                "raw": raw,
            }
    else:
        overall = overall_match.group(1).upper()

    score_match = re.search(r"SCORE\s*:\s*([0-5])", raw, flags=re.IGNORECASE)
    score = int(score_match.group(1)) if score_match else (5 if overall == "PASS" else 0)

    reason_match = re.search(r"REASON\s*:\s*(.+)", raw, flags=re.IGNORECASE | re.DOTALL)
    reason = reason_match.group(1).strip() if reason_match else raw.strip()

    return {
        "passed": overall == "PASS",
        "score": score,
        "reason": reason,
        "raw": raw,
    }


@langfuse.observe(
    name="llm.judge",
    as_type="generation",
    capture_input=False,
    capture_output=False,
)
def judge_answer(case: dict, answer: str, tool_events: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM-as-Judge로 답변 의미를 평가."""
    rubric = _format_rubric(case["expected"])
    tool_evidence = _compact_tool_events(tool_events)

    prompt = f"""
당신은 agent 답변을 평가하는 엄격한 품질 평가자입니다.
아래 기준으로 답변을 평가하세요.

반드시 다음 형식으로만 답하세요:
OVERALL: PASS 또는 FAIL
SCORE: 0~5 사이 정수
GROUNDING: PASS/PARTIAL/FAIL - 근거성 평가
CORRECTNESS: PASS/PARTIAL/FAIL - 사실 정확성 평가
COMPLETENESS: PASS/PARTIAL/FAIL - 질문 충족도 평가
REASON: 짧은 한국어 총평

평가 원칙:
- 표현이 조금 달라도 의미가 맞으면 통과입니다.
- 숫자, user_id, 에러명처럼 rubric에 명시된 사실은 엄격히 봅니다.
- tool evidence에 없는 정보를 단정적으로 만들어내면 FAIL입니다.
- 답변이 짧아도 질문과 rubric을 만족하면 PASS입니다.
- 사용자가 추정을 요구하더라도 tool evidence가 없으면 추정 정보를 제공하지 않아야 합니다.
- tool 호출 여부 자체는 별도 deterministic check가 있으므로, 여기서는 답변 품질을 평가합니다.
- 각 항목은 짧게 쓰고, REASON은 한 문장으로 끝내세요.

[Case ID]
{case["id"]}

[사용자 입력]
{case["input"]}

[Tool evidence]
{json.dumps(tool_evidence, ensure_ascii=False, indent=2)}

[Rubric]
{rubric}

[Agent 답변]
{answer}
""".strip()

    langfuse.get_client().update_current_generation(
        input={
            "case_id": case["id"],
            "rubric": rubric,
            "tool_evidence": tool_evidence,
            "answer_preview": answer[:700],
        },
        model=JUDGE_MODEL,
        metadata={"role": "llm_as_judge"},
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            seed=1,
            max_output_tokens=1024,
        ),
    )

    raw = response.text or ""
    parsed = _parse_judge_text(raw)

    usage_details = agent._usage_details(response)
    langfuse.get_client().update_current_generation(
        output=parsed,
        model=JUDGE_MODEL,
        usage_details=usage_details,
        cost_details=agent._cost_details(usage_details),
    )

    return parsed


def evaluate_one(case: dict) -> dict:
    original_handlers = dict(agent.HANDLERS)
    tool_events = _wrap_handlers_for_tracking()
    try:
        answer = react_loop(case["input"], max_steps=5)
        tools_passed, reasons = check_tools(tool_events, case["expected"])
        judge = judge_answer(case, answer, tool_events)
        min_score = int(case["expected"].get("min_score", 5))
        quality_passed = judge["passed"] and int(judge.get("score", 0)) >= min_score

        if not judge["passed"]:
            reasons.append(f"Judge 실패: {judge['reason']}")
        elif int(judge.get("score", 0)) < min_score:
            reasons.append(f"Judge 점수 부족: {judge.get('score')} < min_score={min_score}")

        return {
            "id": case["id"],
            "input": case["input"],
            "passed": tools_passed and quality_passed,
            "answer": answer,
            "tools": _tool_names(tool_events),
            "tool_events": _compact_tool_events(tool_events),
            "judge": judge,
            "reasons": reasons,
            "notes": case.get("notes"),
        }
    except Exception as e:
        return {
            "id": case["id"],
            "input": case["input"],
            "passed": False,
            "answer": None,
            "tools": _tool_names(tool_events),
            "tool_events": _compact_tool_events(tool_events),
            "judge": None,
            "reasons": [f"실행/평가 에러: {type(e).__name__}: {e}"],
            "notes": case.get("notes"),
        }
    finally:
        # 다음 case에서 wrapper가 중첩되지 않도록 원래 handler로 복원.
        agent.HANDLERS.clear()
        agent.HANDLERS.update(original_handlers)


def _write_report(results: list[dict], cases: list[dict], mode: str) -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    passed_n = sum(1 for result in results if result["passed"])
    total = len(results)
    now = datetime.now().isoformat(timespec="seconds")

    report = {
        "generated_at": now,
        "summary": {
            "passed": passed_n,
            "total": total,
            "pass_rate": passed_n / total if total else 0,
            "judge_model": JUDGE_MODEL,
            "mode": mode,
        },
        "results": results,
    }
    (REPORT_DIR / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Evaluation Report",
        "",
        f"Generated: `{now}`",
        f"Judge model: `{JUDGE_MODEL}`",
        f"Mode: `{mode}`",
        f"Summary: **{passed_n}/{total} passed**",
        "",
        "| Case | Result | Score | Tools | Reason |",
        "|---|---:|---:|---|---|",
    ]
    for result in results:
        judge = result.get("judge") or {}
        result_icon = "✅" if result["passed"] else "❌"
        score = judge.get("score", "-")
        reason = "; ".join(result["reasons"]) or judge.get("reason", "")
        lines.append(
            f"| `{result['id']}` | {result_icon} | {score} | `{result['tools']}` | {reason[:180]} |"
        )

    for result in results:
        judge = result.get("judge") or {}
        lines.extend(
            [
                "",
                f"## {result['id']}",
                "",
                f"**Input**: {result['input']}",
                "",
                f"**Answer**: {result.get('answer')}",
                "",
                "**Tool events**:",
                "```json",
                json.dumps(result.get("tool_events"), ensure_ascii=False, indent=2),
                "```",
                "",
                "**Judge raw output**:",
                "```text",
                str(judge.get("raw", "")),
                "```",
            ]
        )

    (REPORT_DIR / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run golden dataset quality evaluation.")
    parser.add_argument(
        "--simulate-regression",
        action="store_true",
        help="Temporarily weaken the system prompt so the eval can demonstrate a failure.",
    )
    args = parser.parse_args()

    mode = "simulated-regression" if args.simulate_regression else "baseline"
    if args.simulate_regression:
        agent.SYSTEM_INSTRUCTION += SIMULATED_REGRESSION_PROMPT
        print("⚠️  Simulated regression mode: system prompt now encourages guessing when data is missing.\n")

    cases = yaml.safe_load(Path(__file__).parent.joinpath("golden_set.yaml").read_text(encoding="utf-8"))
    print(f"=== Evaluating {len(cases)} cases ({mode}) ===\n")

    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} — {case['input'][:60]}")
        result = evaluate_one(case)
        results.append(result)
        symbol = "✅" if result["passed"] else "❌"
        score = result["judge"].get("score") if result.get("judge") else "-"
        print(f"  {symbol} score={score} tools={result['tools']}")
        if result["answer"]:
            print(f"     answer: {result['answer'][:120]}")
        if result.get("judge"):
            print(f"     judge: {result['judge']['reason'][:180]}")
        if result["reasons"]:
            for reason in result["reasons"]:
                print(f"     · {reason}")
        print()

    passed_n = sum(1 for result in results if result["passed"])
    total = len(results)
    _write_report(results, cases, mode)
    print(f"=== Summary: {passed_n}/{total} passed ({passed_n / total * 100:.0f}%) ===")
    print("Report written to .eval/latest.md and .eval/latest.json")
    langfuse.get_client().flush()
