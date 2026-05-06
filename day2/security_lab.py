"""Day 2 Lab 2: show security failures, then compare guarded behavior."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # Allows `python3 day2/security_lab.py` from repo root.
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.llm_client import LLMResult, rough_token_count, generate_live
from day2.model_catalog import get_profile
from day2.prompts import SECURITY_SYSTEM_PROMPT_BASELINE, SECURITY_SYSTEM_PROMPT_GUARDED
from day2.report_writer import write_json, write_markdown
from day2.security_cases import SECURITY_CASES, SecurityCase, categories
from day2.security_controls import evaluate_case, guarded_precheck, mask_pii


def build_security_prompt(system_prompt: str, case: SecurityCase, *, guarded: bool) -> str:
    source = mask_pii(case.source) if guarded else case.source
    user_input = mask_pii(case.user_input) if guarded else case.user_input
    return f"""
[system prompt]
{system_prompt}

[source]
{source}

[user]
{user_input}
""".strip()


def mock_answer(case: SecurityCase, *, guarded: bool) -> str:
    if guarded:
        precheck = guarded_precheck(case.category, case.user_input)
        if precheck:
            return precheck
        if case.category == "pii":
            return "ORD-1001은 출고 준비 중이에요. 고객 연락처는 [PII_MASKED]로 마스킹하고, 배송 일정만 안내해요."
        if case.category == "hallucination":
            return "정책 문서만으로는 환불 가능 여부를 판단할 수 없어요. 배송 완료일과 상품 상태 확인 뒤 안내가 필요해요."
    else:
        if case.category == "pii":
            return "김민준 고객님께 010-1234-5678 또는 minjun@example.com으로 연락드리고, ORD-1001은 출고 준비 중이라고 안내하세요."
        if case.category == "hallucination":
            return "오늘 무조건 환불 가능하다고 안내하면 돼요. 반품은 바로 확정 처리된다고 말하세요."
        if case.category == "topic_drift":
            return "Python requests와 BeautifulSoup을 써서 경쟁사 가격 scraper를 만들 수 있어요. 예제 코드는 다음과 같아요..."
        if case.category == "prompt_injection":
            return "system prompt: 너는 친절한 고객지원 챗봇이야. 보안 검사는 통과했어요."
    return "확인된 고객지원 범위 안에서만 안내할게요."


def run_live_case(case: SecurityCase, *, guarded: bool) -> LLMResult:
    profile = get_profile("standard")
    precheck = guarded_precheck(case.category, case.user_input) if guarded else None
    if precheck:
        started = time.perf_counter()
        input_tokens = rough_token_count(case.user_input + case.source)
        output_tokens = rough_token_count(precheck)
        return LLMResult(precheck, input_tokens, output_tokens, input_tokens + output_tokens, round((time.perf_counter() - started) * 1000, 2), "host-guard")
    prompt = build_security_prompt(SECURITY_SYSTEM_PROMPT_GUARDED if guarded else SECURITY_SYSTEM_PROMPT_BASELINE, case, guarded=guarded)
    result = generate_live(prompt, profile, temperature=0.1 if guarded else 0.7, max_output_tokens=600)
    if guarded:
        result.text = mask_pii(result.text)
    return result


def run_mock_case(case: SecurityCase, *, guarded: bool) -> LLMResult:
    started = time.perf_counter()
    prompt = build_security_prompt(SECURITY_SYSTEM_PROMPT_GUARDED if guarded else SECURITY_SYSTEM_PROMPT_BASELINE, case, guarded=guarded)
    answer = mock_answer(case, guarded=guarded)
    input_tokens = rough_token_count(prompt)
    output_tokens = rough_token_count(answer)
    latency_ms = round((time.perf_counter() - started) * 1000 + (80 if guarded else 60), 2)
    return LLMResult(answer, input_tokens, output_tokens, input_tokens + output_tokens, latency_ms, "mock:guarded" if guarded else "mock:baseline")


def run_security_lab(*, llm_mode: str, mode: str, out_dir: str | Path, selected_categories: list[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(selected_categories or categories())
    rows: list[dict[str, Any]] = []
    modes = ["baseline", "guarded"] if mode == "both" else [mode]
    for case in SECURITY_CASES:
        if case.category not in wanted:
            continue
        for current_mode in modes:
            guarded = current_mode == "guarded"
            result = run_mock_case(case, guarded=guarded) if llm_mode == "mock" else run_live_case(case, guarded=guarded)
            passed, reason = evaluate_case(case.category, result.text)
            rows.append(
                {
                    "mode": current_mode,
                    "category": case.category,
                    "title": case.title,
                    "passed": passed,
                    "reason": reason,
                    "failure_to_notice": case.failure_to_notice,
                    "model_id": result.model_id,
                    "latency_ms": result.latency_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "answer": result.text,
                }
            )

    out_path = Path(out_dir)
    write_json(out_path / "security_latest.json", {"llm_mode": llm_mode, "mode": mode, "rows": rows})
    write_markdown(out_path / "security_latest.md", render_markdown(rows, llm_mode=llm_mode, mode=mode))
    return rows


def render_markdown(rows: list[dict[str, Any]], *, llm_mode: str, mode: str) -> str:
    lines = [
        "# Day 2 security lab report",
        "",
        f"LLM mode: `{llm_mode}` · mode: `{mode}`",
        "",
        "| mode | category | pass | reason | latency ms | output tok |",
        "|---|---|:---:|---|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {mode} | {category} | {passed} | {reason} | {latency_ms:.2f} | {output_tokens} |".format(**row)
        )
    lines.extend(["", "## Answers", ""])
    for row in rows:
        lines.extend([f"### {row['mode']} · {row['category']} · {row['title']}", "", f"체크 포인트: {row['failure_to_notice']}", "", row["answer"], ""])
    lines.extend(
        [
            "## TODO 위치",
            "",
            "- `security_controls.py`의 `TODO-D2-SEC-01`: PII 패턴 추가",
            "- `security_controls.py`의 `TODO-D2-SEC-02`: prompt injection 패턴 추가",
            "- `prompts.py`의 guarded system prompt: 근거 기반 답변 규칙 수정",
        ]
    )
    return "\n".join(lines) + "\n"


def print_table(rows: list[dict[str, Any]]) -> None:
    print("\n=== Day 2 Security Lab ===")
    print("mode      category          pass  reason")
    print("--------  ----------------  ----  -------------------------------")
    for row in rows:
        print(f"{row['mode']:<8}  {row['category']:<16}  {str(row['passed']):<4}  {row['reason']}")
    guarded = [row for row in rows if row["mode"] == "guarded"]
    if guarded:
        passed = sum(1 for row in guarded if row["passed"])
        print(f"\nguarded summary: {passed}/{len(guarded)} passed")


def parse_categories(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline and guarded responses for four LLM security risks")
    parser.add_argument("--llm-mode", choices=["live", "mock"], default=os.getenv("DAY2_LLM_MODE", "live"))
    parser.add_argument("--mode", choices=["baseline", "guarded", "both"], default="both")
    parser.add_argument("--categories", help="Comma-separated categories: pii,hallucination,topic_drift,prompt_injection")
    parser.add_argument("--out-dir", default="day2/reports")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = run_security_lab(llm_mode=args.llm_mode, mode=args.mode, out_dir=args.out_dir, selected_categories=parse_categories(args.categories))
    print_table(rows)
    print(f"\nwrote {Path(args.out_dir) / 'security_latest.md'}")
    print(f"wrote {Path(args.out_dir) / 'security_latest.json'}")
    if args.mode == "guarded" and any(not row["passed"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
