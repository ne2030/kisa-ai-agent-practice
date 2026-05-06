"""Day 2 Lab 1: run one cost experiment at a time.

Students intentionally change one variable per run:
- case
- model profile
- prompt style

Then cost_eval.py scores the saved output against the golden dataset.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # Allows `python3 day2/cost_lab.py` from repo root.
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.cost_dataset import default_case_id, get_cost_case, load_cost_cases
from day2.llm_client import generate_text
from day2.model_catalog import estimate_cost_usd, get_profile, profile_names
from day2.prompts import COST_PROMPT_STYLES
from day2.report_writer import write_json, write_markdown


def build_prompt(system_prompt: str, input_text: str, *, case_id: str, prompt_style: str) -> str:
    return f"""
[case]
{case_id}

[prompt style]
{prompt_style}

[system prompt]
{system_prompt}

[input]
{input_text}
""".strip()


def run_cost_lab(
    *,
    case_id: str,
    profile_name: str,
    prompt_style: str,
    llm_mode: str,
    out_dir: str | Path,
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
) -> dict[str, Any]:
    case = get_cost_case(case_id)
    profile = get_profile(profile_name)
    system_prompt = COST_PROMPT_STYLES[prompt_style]
    input_text = str(case["input"]).strip()
    prompt = build_prompt(system_prompt, input_text, case_id=case_id, prompt_style=prompt_style)

    result = generate_text(
        prompt,
        profile,
        llm_mode=llm_mode,
        purpose="cost",
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    cost = estimate_cost_usd(profile, result.input_tokens, result.output_tokens, cached_input_tokens=result.cached_input_tokens)
    row = {
        "case_id": case_id,
        "case_title": case.get("title", case_id),
        "task_type": case.get("task_type", ""),
        "prompt_style": prompt_style,
        "profile": profile.name,
        "label": profile.label,
        "model_id": result.model_id,
        "expected_style": profile.expected_style,
        "latency_ms": result.latency_ms,
        "input_tokens": result.input_tokens,
        "visible_output_tokens": result.visible_output_tokens,
        "thinking_tokens": result.thinking_tokens,
        "output_tokens": result.output_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "total_tokens": result.total_tokens,
        "estimated_cost_usd": cost,
        "finish_reason": result.finish_reason,
        "warnings": result.warnings,
        "output": result.text,
    }

    out_path = Path(out_dir)
    report = {
        "llm_mode": llm_mode,
        "case_id": case_id,
        "profile": profile.name,
        "prompt_style": prompt_style,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "system_prompt": system_prompt,
        "input_text": input_text,
        "rows": [row],
    }
    write_json(out_path / "cost_latest.json", report)
    write_markdown(out_path / "cost_latest.md", render_markdown(row, llm_mode=llm_mode))
    return row


def render_markdown(row: dict[str, Any], *, llm_mode: str) -> str:
    lines = [
        "# Day 2 cost lab report",
        "",
        f"LLM mode: `{llm_mode}`",
        f"Case: `{row['case_id']}` — {row['case_title']}",
        f"Prompt style: `{row['prompt_style']}`",
        "",
        "| profile | model | latency ms | input | visible output | thinking | cached input | total | est. cost | finish |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        "| {profile} | {model_id} | {latency_ms:.2f} | {input_tokens} | {visible_output_tokens} | {thinking_tokens} | {cached_input_tokens} | {total_tokens} | ${estimated_cost_usd:.8f} | {finish_reason} |".format(**row),
        "",
    ]
    if row.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in row["warnings"])
        lines.append("")
    lines.extend([
        "## Output",
        "",
        row.get("output") or "[visible output 없음]",
        "",
        "## 볼 것",
        "",
        "- input token은 system prompt와 원문 길이에 따라 달라져요.",
        "- visible output token은 실제 화면에 보이는 답변 길이에 가까워요.",
        "- thinking token은 화면에 안 보이지만 output 비용에 들어가요.",
        "- cached input token은 cache hit가 난 입력 token이에요.",
        "- 비용은 provider usage metadata와 가격표를 이용한 추정값이에요.",
    ])
    return "\n".join(lines) + "\n"


def print_row(row: dict[str, Any]) -> None:
    print("\n=== Day 2 Cost Lab ===")
    print("case     profile   style       model                         latency  input  visible  think  cached  total   est.cost")
    print("-------  --------  ----------  ----------------------------  -------  -----  -------  -----  ------  ------  ----------")
    print(
        f"{row['case_id'][:7]:<7}  {row['profile']:<8}  {row['prompt_style']:<10}  {row['model_id']:<28}  "
        f"{row['latency_ms']:>7.1f}  {row['input_tokens']:>5}  {row['visible_output_tokens']:>7}  "
        f"{row['thinking_tokens']:>5}  {row['cached_input_tokens']:>6}  {row['total_tokens']:>6}  ${row['estimated_cost_usd']:.8f}"
    )
    if row.get("warnings"):
        print("\nWarnings:")
        for warning in row["warnings"]:
            print(f"- {warning}")
    print(f"\n--- {row['profile']} / {row['model_id']} / {row['prompt_style']} ---")
    print(row.get("output") or "[visible output 없음]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one model/prompt cost experiment and save a report")
    parser.add_argument("--case", default=default_case_id(), help="Golden case id from day2/cost_golden_set.yaml")
    parser.add_argument("--profile", choices=profile_names(), default="cheap", help="One profile to run: cheap, standard, strong")
    parser.add_argument("--prompt-style", choices=sorted(COST_PROMPT_STYLES), default="structured")
    parser.add_argument("--llm-mode", choices=["live", "mock"], default=os.getenv("DAY2_LLM_MODE", "live"))
    parser.add_argument("--out-dir", default="day2/reports")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--list-cases", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_cases:
        for case in load_cost_cases():
            print(f"{case['id']}	{case.get('title', '')}")
        return

    try:
        row = run_cost_lab(
            case_id=args.case,
            profile_name=args.profile,
            prompt_style=args.prompt_style,
            llm_mode=args.llm_mode,
            out_dir=args.out_dir,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
    except RuntimeError as exc:
        print(f"실행 실패: {exc}")
        raise SystemExit(1) from exc
    print_row(row)
    print(f"\nwrote {Path(args.out_dir) / 'cost_latest.md'}")
    print(f"wrote {Path(args.out_dir) / 'cost_latest.json'}")


if __name__ == "__main__":
    main()
