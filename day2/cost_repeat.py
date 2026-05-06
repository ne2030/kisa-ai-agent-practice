"""같은 조건을 여러 번 실행해서 응답 흔들림을 확인해요."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.cost_dataset import default_case_id, get_cost_case
from day2.cost_eval import evaluate_row
from day2.cost_lab import build_prompt
from day2.llm_client import generate_text
from day2.model_catalog import estimate_cost_usd, get_profile, profile_names
from day2.prompts import COST_PROMPT_STYLES
from day2.report_writer import write_json, write_markdown


def run_one(
    *,
    run_index: int,
    case_id: str,
    profile_name: str,
    prompt_style: str,
    llm_mode: str,
    temperature: float,
    max_output_tokens: int,
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
    row = {
        "run_index": run_index,
        "case_id": case_id,
        "case_title": case.get("title", case_id),
        "task_type": case.get("task_type", ""),
        "prompt_style": prompt_style,
        "profile": profile.name,
        "label": profile.label,
        "model_id": result.model_id,
        "latency_ms": result.latency_ms,
        "input_tokens": result.input_tokens,
        "visible_output_tokens": result.visible_output_tokens,
        "thinking_tokens": result.thinking_tokens,
        "output_tokens": result.output_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "total_tokens": result.total_tokens,
        "estimated_cost_usd": estimate_cost_usd(profile, result.input_tokens, result.output_tokens, cached_input_tokens=result.cached_input_tokens),
        "finish_reason": result.finish_reason,
        "warnings": result.warnings,
        "output": result.text,
    }
    row["eval"] = evaluate_row(row)
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [int(row["eval"]["score"]) for row in rows]
    visible_tokens = [int(row["visible_output_tokens"]) for row in rows]
    costs = [float(row["estimated_cost_usd"]) for row in rows]
    latencies = [float(row["latency_ms"]) for row in rows]
    return {
        "runs": len(rows),
        "passed": sum(1 for row in rows if row["eval"]["passed"]),
        "score_min": min(scores),
        "score_max": max(scores),
        "visible_output_min": min(visible_tokens),
        "visible_output_max": max(visible_tokens),
        "avg_cost_usd": round(mean(costs), 8),
        "avg_latency_ms": round(mean(latencies), 2),
    }


def render_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    first = rows[0]
    lines = [
        "# Day 2 cost repeat report",
        "",
        f"Case: `{first['case_id']}`",
        f"Profile: `{first['profile']}`",
        f"Prompt style: `{first['prompt_style']}`",
        "",
        "## 요약",
        "",
        "| runs | passed | score range | visible output range | avg cost | avg latency |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {summary['runs']} | {summary['passed']} | {summary['score_min']}–{summary['score_max']} | {summary['visible_output_min']}–{summary['visible_output_max']} | ${summary['avg_cost_usd']:.8f} | {summary['avg_latency_ms']:.1f} |",
        "",
        "## 실행별 결과",
        "",
        "| run | result | score | visible | thinking | cost | latency | missing terms |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        eval_result = row["eval"]
        icon = "✅" if eval_result["passed"] else "❌"
        missing = ", ".join(str(term) for term in eval_result["missing_required"]) or "-"
        lines.append(
            f"| {row['run_index']} | {icon} | {eval_result['score']}/{eval_result['min_score']} | {row['visible_output_tokens']} | {row['thinking_tokens']} | ${row['estimated_cost_usd']:.8f} | {row['latency_ms']:.1f} | {missing} |"
        )
    lines.extend(["", "## 출력 미리보기", ""])
    for row in rows:
        lines.extend([
            f"### Run {row['run_index']}",
            "",
            row["output"][:900],
            "",
        ])
    return "\n".join(lines) + "\n"


def run_repeat(
    *,
    case_id: str,
    profile_name: str,
    prompt_style: str,
    runs: int,
    llm_mode: str,
    out_dir: str | Path,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    rows = [
        run_one(
            run_index=index,
            case_id=case_id,
            profile_name=profile_name,
            prompt_style=prompt_style,
            llm_mode=llm_mode,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        for index in range(1, runs + 1)
    ]
    summary = summarize(rows)
    payload = {
        "case_id": case_id,
        "profile": profile_name,
        "prompt_style": prompt_style,
        "llm_mode": llm_mode,
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "summary": summary,
        "rows": rows,
    }
    out_path = Path(out_dir)
    write_json(out_path / "cost_repeat_latest.json", payload)
    write_markdown(out_path / "cost_repeat_latest.md", render_markdown(rows, summary))
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("\n=== Day 2 Cost Repeat ===")
    print(f"case={payload['case_id']} profile={payload['profile']} style={payload['prompt_style']} runs={summary['runs']}")
    print(f"passed={summary['passed']}/{summary['runs']} score_range={summary['score_min']}–{summary['score_max']} visible_range={summary['visible_output_min']}–{summary['visible_output_max']}")
    print("run  pass  score  visible  think  cost        missing")
    print("---  ----  -----  -------  -----  ----------  ----------------")
    for row in payload["rows"]:
        eval_result = row["eval"]
        icon = "Y" if eval_result["passed"] else "N"
        missing = ", ".join(str(term) for term in eval_result["missing_required"]) or "-"
        print(f"{row['run_index']:>3}  {icon:<4}  {eval_result['score']}/{eval_result['min_score']}    {row['visible_output_tokens']:>7}  {row['thinking_tokens']:>5}  ${row['estimated_cost_usd']:.8f}  {missing}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="같은 조건을 여러 번 실행하고 품질과 비용 흔들림을 비교")
    parser.add_argument("--case", default=default_case_id(), help="day2/cost_golden_set.yaml의 case id")
    parser.add_argument("--profile", choices=profile_names(), default="standard")
    parser.add_argument("--prompt-style", choices=sorted(COST_PROMPT_STYLES), default="naive")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--llm-mode", choices=["live", "mock"], default=os.getenv("DAY2_LLM_MODE", "live"))
    parser.add_argument("--out-dir", default="day2/reports")
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        payload = run_repeat(
            case_id=args.case,
            profile_name=args.profile,
            prompt_style=args.prompt_style,
            runs=max(1, args.runs),
            llm_mode=args.llm_mode,
            out_dir=args.out_dir,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        )
    except RuntimeError as exc:
        print(f"실행 실패: {exc}")
        raise SystemExit(1) from exc
    print_summary(payload)
    print(f"\nwrote {Path(args.out_dir) / 'cost_repeat_latest.md'}")
    print(f"wrote {Path(args.out_dir) / 'cost_repeat_latest.json'}")


if __name__ == "__main__":
    main()
