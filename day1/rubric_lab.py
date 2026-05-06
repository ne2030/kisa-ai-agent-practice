"""Rubric 개선 미니 실습.

같은 bad_answer를 약한 rubric과 강한 rubric으로 각각 평가합니다.
목표는 "rubric을 어떻게 써야 quality regression을 잡는가"를 직접 보는 것입니다.

실행:
    python3 rubric_lab.py

결과:
    .eval/rubric_lab.md
"""

from __future__ import annotations

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

REPORT_DIR = Path(__file__).parent / ".eval"
JUDGE_MODEL = agent.MODEL_NAME


def _format_rubric(rubric: dict[str, str]) -> str:
    return "\n".join(f"- {name}: {criteria}" for name, criteria in rubric.items())


def _parse_judge_text(raw: str) -> dict[str, Any]:
    overall_match = re.search(r"OVERALL\s*:\s*(PASS|FAIL)", raw, flags=re.IGNORECASE)
    score_match = re.search(r"SCORE\s*:\s*([0-5])", raw, flags=re.IGNORECASE)
    reason_match = re.search(r"REASON\s*:\s*(.+)", raw, flags=re.IGNORECASE | re.DOTALL)
    overall = overall_match.group(1).upper() if overall_match else "FAIL"
    return {
        "passed": overall == "PASS",
        "score": int(score_match.group(1)) if score_match else (5 if overall == "PASS" else 0),
        "reason": reason_match.group(1).strip() if reason_match else raw.strip(),
        "raw": raw,
    }


@langfuse.observe(
    name="rubric_lab.judge",
    as_type="generation",
    capture_input=False,
    capture_output=False,
)
def judge_with_rubric(label: str, fixture: dict[str, Any], rubric: dict[str, str]) -> dict[str, Any]:
    """주어진 rubric만 기준으로 bad_answer를 평가."""
    rubric_text = _format_rubric(rubric)
    prompt = f"""
당신은 agent 답변 평가자입니다.
반드시 아래 Rubric에 명시된 기준만 사용해서 평가하세요.
Rubric에 없는 요구사항을 임의로 추가하지 마세요.

반드시 다음 형식으로만 답하세요:
OVERALL: PASS 또는 FAIL
SCORE: 0~5 사이 정수
REASON: 20자 이내의 짧은 한국어 근거

추가 규칙:
- REASON은 "조건 충족" 또는 "근거 없는 추정 포함"처럼 짧은 명사구로 끝내세요.
- REASON을 길게 설명하지 마세요.

[사용자 입력]
{fixture["input"]}

[Tool evidence]
{json.dumps(fixture["tool_evidence"], ensure_ascii=False, indent=2)}

[Rubric]
{rubric_text}

[Agent 답변]
{fixture["bad_answer"]}
""".strip()

    langfuse.get_client().update_current_generation(
        input={
            "label": label,
            "rubric": rubric_text,
            "answer": fixture["bad_answer"],
            "tool_evidence": fixture["tool_evidence"],
        },
        model=JUDGE_MODEL,
        metadata={"role": "rubric_lab_judge"},
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
    parsed = _parse_judge_text(response.text or "")

    usage_details = agent._usage_details(response)
    langfuse.get_client().update_current_generation(
        output=parsed,
        model=JUDGE_MODEL,
        usage_details=usage_details,
        cost_details=agent._cost_details(usage_details),
    )
    return parsed


def write_report(fixture: dict[str, Any], results: dict[str, dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Rubric Lab Report",
        "",
        f"Generated: `{now}`",
        f"Case: `{fixture['id']}`",
        "",
        "## Bad answer under test",
        "",
        fixture["bad_answer"].strip(),
        "",
        "## Results",
        "",
        "| Rubric | Result | Score | Reason |",
        "|---|---:|---:|---|",
    ]
    for label, result in results.items():
        icon = "✅ PASS" if result["passed"] else "❌ FAIL"
        lines.append(f"| `{label}` | {icon} | {result['score']} | {result['reason']} |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- weak_rubric이 PASS라면, rubric이 너무 느슨해서 bad answer를 잡지 못한 것입니다.",
            "- strong_rubric이 FAIL이라면, grounding 기준이 bad answer를 잡아낸 것입니다.",
            "- 실습 목표는 weak_rubric을 직접 고쳐서 bad answer를 FAIL시키는 것입니다.",
            "",
        ]
    )
    (REPORT_DIR / "rubric_lab.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    fixture = yaml.safe_load(Path("rubric_lab.yaml").read_text(encoding="utf-8"))
    results = {
        "weak_rubric": judge_with_rubric("weak_rubric", fixture, fixture["weak_rubric"]),
        "strong_rubric": judge_with_rubric("strong_rubric", fixture, fixture["strong_rubric"]),
    }

    print("=== Rubric Lab ===")
    for label, result in results.items():
        icon = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{label}: {icon} score={result['score']} — {result['reason']}")

    write_report(fixture, results)
    print("Report written to .eval/rubric_lab.md")
    langfuse.get_client().flush()
