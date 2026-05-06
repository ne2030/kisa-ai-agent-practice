"""Day 2 Lab 1: compare model quality, tokens, cost, and latency."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # Allows `python3 day2/cost_lab.py` from repo root.
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.llm_client import generate_text
from day2.model_catalog import estimate_cost_usd, get_profile, profile_names
from day2.prompts import COST_INPUT_TEXT, COST_SYSTEM_PROMPT
from day2.report_writer import write_json, write_markdown


def build_prompt(system_prompt: str, input_text: str) -> str:
    return f"""
[system prompt]
{system_prompt}

[input]
{input_text}
""".strip()


def parse_models(value: str) -> list[str]:
    names = [part.strip() for part in value.split(",") if part.strip()]
    return names or profile_names()


def run_cost_lab(*, models: list[str], llm_mode: str, out_dir: str | Path, system_prompt: str = COST_SYSTEM_PROMPT, input_text: str = COST_INPUT_TEXT) -> list[dict[str, Any]]:
    prompt = build_prompt(system_prompt, input_text)
    rows: list[dict[str, Any]] = []
    for name in models:
        profile = get_profile(name)
        result = generate_text(prompt, profile, llm_mode=llm_mode, purpose="cost")
        cost = estimate_cost_usd(profile, result.input_tokens, result.output_tokens)
        rows.append(
            {
                "profile": profile.name,
                "label": profile.label,
                "model_id": result.model_id,
                "expected_style": profile.expected_style,
                "latency_ms": result.latency_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
                "estimated_cost_usd": cost,
                "output": result.text,
            }
        )

    out_path = Path(out_dir)
    write_json(out_path / "cost_latest.json", {"llm_mode": llm_mode, "system_prompt": system_prompt, "input_text": input_text, "rows": rows})
    write_markdown(out_path / "cost_latest.md", render_markdown(rows, llm_mode=llm_mode))
    return rows


def render_markdown(rows: list[dict[str, Any]], *, llm_mode: str) -> str:
    lines = [
        "# Day 2 cost lab report",
        "",
        f"LLM mode: `{llm_mode}`",
        "",
        "| profile | model | latency ms | input tok | output tok | total tok | est. cost |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {profile} | {model_id} | {latency_ms:.2f} | {input_tokens} | {output_tokens} | {total_tokens} | ${estimated_cost_usd:.8f} |".format(**row)
        )
    lines.extend(["", "## Outputs", ""])
    for row in rows:
        lines.extend([f"### {row['profile']} · {row['model_id']}", "", row["output"], ""])
    lines.extend(
        [
            "## 볼 것",
            "",
            "- 싼 모델이 항상 나쁜 건 아니지만, 누락/압축/표현 방식이 달라질 수 있어요.",
            "- 같은 input이어도 output token이 길어지면 비용이 커져요.",
            "- latency는 모델 크기와 네트워크 상태를 함께 봐야 해요.",
            "- 이 가격은 실습용 추정값이에요. 실제 과금 전에는 provider 가격표를 다시 확인해요.",
        ]
    )
    return "\n".join(lines) + "\n"


def print_table(rows: list[dict[str, Any]]) -> None:
    print("\n=== Day 2 Cost Lab ===")
    print("profile   model                         latency  input  output  total   est.cost")
    print("--------  ----------------------------  -------  -----  ------  ------  ----------")
    for row in rows:
        print(
            f"{row['profile']:<8}  {row['model_id']:<28}  {row['latency_ms']:>7.1f}  {row['input_tokens']:>5}  {row['output_tokens']:>6}  {row['total_tokens']:>6}  ${row['estimated_cost_usd']:.8f}"
        )
    print("\nOutputs:")
    for row in rows:
        print(f"\n--- {row['profile']} / {row['model_id']} ---")
        print(row["output"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare model output, tokens, cost, and latency on one summarization task")
    parser.add_argument("--models", default="cheap,standard,strong", help="Comma-separated profiles: cheap,standard,strong")
    parser.add_argument("--llm-mode", choices=["live", "mock"], default=os.getenv("DAY2_LLM_MODE", "live"))
    parser.add_argument("--out-dir", default="day2/reports")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = run_cost_lab(models=parse_models(args.models), llm_mode=args.llm_mode, out_dir=args.out_dir)
    print_table(rows)
    print(f"\nwrote {Path(args.out_dir) / 'cost_latest.md'}")
    print(f"wrote {Path(args.out_dir) / 'cost_latest.json'}")


if __name__ == "__main__":
    main()
