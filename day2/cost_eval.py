"""비용 실습 결과를 기준 데이터셋으로 평가해요."""

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


def _score_to_status(score: int) -> str:
    if score >= 4:
        return "PASS"
    if score >= 2:
        return "PARTIAL"
    return "FAIL"


def _term_score(found: list[Any], total: int) -> int:
    if total <= 0:
        return 5
    return round(len(found) / total * 5)


def _rubric_breakdown(
    *,
    output: str,
    expected: dict[str, Any],
    found_required: list[Any],
    missing_required: list[Any],
    found_forbidden: list[Any],
    prompt_style: str | None,
) -> dict[str, Any]:
    required_terms = list(expected.get("required_terms") or [])
    forbidden_terms = list(expected.get("forbidden_terms") or [])
    rubric = expected.get("rubric") or {}

    correctness_score = _term_score(found_required, len(required_terms))
    if found_forbidden:
        correctness_score = max(0, correctness_score - 1)

    groundedness_score = 5 if not found_forbidden else max(0, 5 - len(found_forbidden) * 2)

    structure_hits = [
        bool(re.search(r"핵심|요약", output)),
        bool(re.search(r"고객|영향", output)),
        bool(re.search(r"다음|조치|안내|확인", output)),
        bool(re.search(r"확실하지|unknown|불확실|필요", output, flags=re.IGNORECASE)),
    ]
    if prompt_style == "json":
        usefulness_score = 5 if _has_json_shape(output) else 2
    else:
        usefulness_score = round(sum(structure_hits) / len(structure_hits) * 5)
        if prompt_style == "naive" and usefulness_score == 5:
            usefulness_score = 4

    items = {
        "correctness": {
            "label": "정확성",
            "criteria": rubric.get("correctness", "required terms 충족 여부"),
            "score": max(0, min(5, correctness_score)),
            "status": _score_to_status(max(0, min(5, correctness_score))),
            "evidence": {
                "found_required": found_required,
                "missing_required": missing_required,
            },
            "comment": "기준어 포함 비율로 계산해요. 중요한 숫자와 조건이 빠지면 점수가 내려가요.",
        },
        "groundedness": {
            "label": "근거성",
            "criteria": rubric.get("groundedness", "금지어와 근거 없는 확정 표현 여부"),
            "score": max(0, min(5, groundedness_score)),
            "status": _score_to_status(max(0, min(5, groundedness_score))),
            "evidence": {
                "found_forbidden": found_forbidden,
                "forbidden_terms": forbidden_terms,
            },
            "comment": "금지어가 나오면 원문에 없는 확정 답변으로 보고 감점해요.",
        },
        "usefulness": {
            "label": "활용성",
            "criteria": rubric.get("usefulness", "운영자가 바로 쓰기 쉬운 구조인지"),
            "score": max(0, min(5, usefulness_score)),
            "status": _score_to_status(max(0, min(5, usefulness_score))),
            "evidence": {
                "structure_hits": {
                    "summary": structure_hits[0],
                    "customer_or_impact": structure_hits[1],
                    "next_action": structure_hits[2],
                    "unknowns_or_checks": structure_hits[3],
                },
                "json_shape": _has_json_shape(output),
            },
            "comment": "요약, 영향, 다음 조치, 확인 필요 항목이 분리되면 점수가 올라가요.",
        },
    }
    average_score = round(sum(item["score"] for item in items.values()) / len(items))
    return {
        "items": items,
        "average_score": average_score,
        "average_status": _score_to_status(average_score),
    }

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
    prompt_style = row.get("prompt_style")

    rubric_breakdown = _rubric_breakdown(
        output=output,
        expected=expected,
        found_required=found_required,
        missing_required=missing_required,
        found_forbidden=found_forbidden,
        prompt_style=prompt_style,
    )
    score = rubric_breakdown["average_score"]
    min_score = int(expected.get("min_score", 4))
    passed = score >= min_score and not found_forbidden

    reasons: list[str] = []
    if missing_required:
        reasons.append(f"빠진 기준어 때문에 점수 하락: {missing_required}")
    if found_forbidden:
        reasons.append(f"금지어 발견: {found_forbidden}")
    if row.get("warnings"):
        reasons.append(f"생성 경고: {row['warnings']}")
    if not reasons:
        reasons.append("기준어와 금지어 확인 통과")

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
            "rubric_breakdown": rubric_breakdown,
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
            f"찾은 기준어: `{result['found_required']}`",
            f"빠진 기준어: `{result['missing_required']}`",
            f"발견된 금지어: `{result['found_forbidden']}`",
            "",
            "### 루브릭별 결과",
            "",
            "| 항목 | 판정 | 점수 | 기준 | 근거 |",
            "|---|---:|---:|---|---|",
        ])
        for key, item in result["quality"]["rubric_breakdown"]["items"].items():
            evidence = json.dumps(item.get("evidence"), ensure_ascii=False)
            lines.append(
                f"| {item['label']} (`{key}`) | {item['status']} | {item['score']}/5 | {item['criteria']} | {evidence[:220]} |"
            )
        lines.extend([
            "",
            "평가 기준 원문:",
            "```json",
            json.dumps(result.get("rubric"), ensure_ascii=False, indent=2),
            "```",
            "",
            "출력 미리보기:",
            "```text",
            result["output_preview"],
            "```",
        ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="cost_lab 결과를 기준 데이터셋으로 평가")
    parser.add_argument("--report", default="day2/reports/cost_latest.json")
    parser.add_argument("--out-dir", default="day2/reports")
    parser.add_argument("--simulate-regression", action="store_true", help="평가 실패 예시를 보기 위해 나쁜 답변으로 바꿔 평가")
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
        for key, item in result["quality"]["rubric_breakdown"]["items"].items():
            print(f"   · {item['label']}({key}): {item['status']} {item['score']}/5")
        for reason in result["reasons"]:
            print(f"   - {reason}")
    print(f"\nwrote {out_dir / 'cost_eval_latest.md'}")
    print(f"wrote {out_dir / 'cost_eval_latest.json'}")


if __name__ == "__main__":
    main()
