"""Evaluate a cost lab output against the Day 2 golden dataset."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.cost_dataset import get_cost_case
from day2.report_writer import write_json, write_markdown


def _contains(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def _has_json_shape(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and stripped.endswith("}")


def evaluate_row(row: dict[str, Any], *, simulate_regression: bool = False) -> dict[str, Any]:
    case = get_cost_case(row["case_id"])
    expected = case.get("expected", {})
    output = row.get("output") or ""
    if simulate_regression:
        output = "배송 문제는 해결됐고 고객에게 전액 보상하면 됩니다. 반품은 무조건 가능해요."

    required_terms = list(expected.get("required_terms") or [])
    forbidden_terms = list(expected.get("forbidden_terms") or [])
    found_required = [term for term in required_terms if _contains(output, str(term))]
    missing_required = [term for term in required_terms if term not in found_required]
    found_forbidden = [term for term in forbidden_terms if _contains(output, str(term))]

    required_score = len(found_required) / len(required_terms) if required_terms else 1.0
    forbidden_penalty = len(found_forbidden) / max(1, len(forbidden_terms))

    format_bonus = 0.0
    prompt_style = row.get("prompt_style")
    if prompt_style == "json":
        format_bonus = 0.5 if _has_json_shape(output) else -0.5
    elif re.search(r"핵심|고객 영향|다음 조치|확실하지", output):
        format_bonus = 0.3

    score = round(max(0, min(5, required_score * 5 - forbidden_penalty * 3 + format_bonus)))
    min_score = int(expected.get("min_score", 4))
    passed = score >= min_score and not found_forbidden

    reasons: list[str] = []
    if missing_required:
        reasons.append(f"missing required terms lowered score: {missing_required}")
    if found_forbidden:
        reasons.append(f"forbidden terms found: {found_forbidden}")
    if row.get("warnings"):
        reasons.append(f"generation warnings: {row['warnings']}")
    if not reasons:
        reasons.append("golden terms and forbidden checks passed")

    return {
        "case_id": row["case_id"],
        "case_title": case.get("title", row["case_id"]),
        "profile": row.get("profile"),
        "prompt_style": prompt_style,
        "model_id": row.get("model_id"),
        "passed": passed,
        "score": score,
        "min_score": min_score,
        "found_required": found_required,
        "missing_required": missing_required,
        "found_forbidden": found_forbidden,
        "reasons": reasons,
        "quality": {
            "required_hit_rate": round(required_score, 3),
            "forbidden_penalty": round(forbidden_penalty, 3),
            "format_bonus": format_bonus,
        },
        "cost": {
            "input_tokens": row.get("input_tokens"),
            "visible_output_tokens": row.get("visible_output_tokens"),
            "thinking_tokens": row.get("thinking_tokens"),
            "total_tokens": row.get("total_tokens"),
            "estimated_cost_usd": row.get("estimated_cost_usd"),
            "latency_ms": row.get("latency_ms"),
        },
        "rubric": expected.get("rubric"),
        "output_preview": output[:700],
    }


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_markdown(results: list[dict[str, Any]], *, report_path: str, mode: str) -> str:
    passed = sum(1 for result in results if result["passed"])
    total = len(results)
    lines = [
        "# Day 2 cost eval report",
        "",
        f"Report: `{report_path}`",
        f"Mode: `{mode}`",
        f"Summary: **{passed}/{total} passed**",
        "",
        "| case | profile | style | result | score | cost | latency | reason |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for result in results:
        icon = "✅" if result["passed"] else "❌"
        cost = result["cost"].get("estimated_cost_usd") or 0
        latency = result["cost"].get("latency_ms") or 0
        reason = "; ".join(result["reasons"])[:180]
        lines.append(
            f"| `{result['case_id']}` | `{result['profile']}` | `{result['prompt_style']}` | {icon} | {result['score']}/{result['min_score']} | ${cost:.8f} | {latency:.1f} | {reason} |"
        )

    for result in results:
        lines.extend([
            "",
            f"## {result['case_id']} · {result['profile']} · {result['prompt_style']}",
            "",
            f"Required found: `{result['found_required']}`",
            f"Required missing: `{result['missing_required']}`",
            f"Forbidden found: `{result['found_forbidden']}`",
            "",
            "Rubric:",
            "```json",
            json.dumps(result.get("rubric"), ensure_ascii=False, indent=2),
            "```",
            "",
            "Output preview:",
            "```text",
            result["output_preview"],
            "```",
        ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate cost_lab output with the golden dataset")
    parser.add_argument("--report", default="day2/reports/cost_latest.json")
    parser.add_argument("--out-dir", default="day2/reports")
    parser.add_argument("--simulate-regression", action="store_true", help="Replace output with a bad answer to show eval failure")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = load_report(args.report)
    mode = "simulated-regression" if args.simulate_regression else "baseline"
    results = [evaluate_row(row, simulate_regression=args.simulate_regression) for row in report.get("rows", [])]

    out_dir = Path(args.out_dir)
    payload = {"mode": mode, "source_report": args.report, "results": results}
    write_json(out_dir / "cost_eval_latest.json", payload)
    write_markdown(out_dir / "cost_eval_latest.md", render_markdown(results, report_path=args.report, mode=mode))

    print("\n=== Day 2 Cost Eval ===")
    for result in results:
        icon = "✅" if result["passed"] else "❌"
        print(
            f"{icon} {result['case_id']} profile={result['profile']} style={result['prompt_style']} "
            f"score={result['score']}/{result['min_score']} cost=${result['cost']['estimated_cost_usd']:.8f}"
        )
        for reason in result["reasons"]:
            print(f"   - {reason}")
    print(f"\nwrote {out_dir / 'cost_eval_latest.md'}")
    print(f"wrote {out_dir / 'cost_eval_latest.json'}")


if __name__ == "__main__":
    main()
