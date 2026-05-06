"""모델 선택, 프롬프트 캐싱, 배치 처리의 월간 비용 영향을 추정해요."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from day2.model_catalog import estimate_cost_usd, get_profile, profile_names
from day2.report_writer import write_json, write_markdown


def _tokens_from_report(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data.get("rows") or []
    return rows[0] if rows else {}


def project_cost(
    *,
    profile_name: str,
    monthly_requests: int,
    input_tokens: int,
    visible_output_tokens: int,
    thinking_tokens: int,
    cache_hit_rate: float,
    cacheable_input_ratio: float,
    batch_ratio: float,
    cache_storage_hours: float,
) -> dict[str, Any]:
    profile = get_profile(profile_name)
    output_tokens = visible_output_tokens + thinking_tokens
    cacheable_tokens = round(input_tokens * cacheable_input_ratio)
    cached_tokens_per_hit = round(cacheable_tokens * cache_hit_rate)

    interactive_requests = round(monthly_requests * (1 - batch_ratio))
    batch_requests = monthly_requests - interactive_requests

    interactive_cost = estimate_cost_usd(
        profile,
        input_tokens * interactive_requests,
        output_tokens * interactive_requests,
        cached_input_tokens=cached_tokens_per_hit * interactive_requests,
        batch=False,
    )
    batch_cost = estimate_cost_usd(
        profile,
        input_tokens * batch_requests,
        output_tokens * batch_requests,
        cached_input_tokens=cached_tokens_per_hit * batch_requests,
        batch=True,
    )
    storage_cost = estimate_cost_usd(
        profile,
        0,
        0,
        cache_storage_tokens=cacheable_tokens if cache_hit_rate else 0,
        cache_storage_hours=cache_storage_hours if cache_hit_rate else 0,
    )
    no_optimization_cost = estimate_cost_usd(profile, input_tokens * monthly_requests, output_tokens * monthly_requests)
    optimized_cost = round(interactive_cost + batch_cost + storage_cost, 8)

    return {
        "profile": profile.name,
        "model_id": profile.model_id,
        "monthly_requests": monthly_requests,
        "input_tokens_per_request": input_tokens,
        "visible_output_tokens_per_request": visible_output_tokens,
        "thinking_tokens_per_request": thinking_tokens,
        "output_tokens_per_request": output_tokens,
        "cache_hit_rate": cache_hit_rate,
        "cacheable_input_ratio": cacheable_input_ratio,
        "cached_tokens_per_request": cached_tokens_per_hit,
        "batch_ratio": batch_ratio,
        "interactive_requests": interactive_requests,
        "batch_requests": batch_requests,
        "no_optimization_cost_usd": no_optimization_cost,
        "optimized_cost_usd": optimized_cost,
        "savings_usd": round(no_optimization_cost - optimized_cost, 8),
        "savings_pct": round((1 - optimized_cost / no_optimization_cost) * 100, 1) if no_optimization_cost else 0,
        "cost_breakdown": {
            "interactive_cost_usd": interactive_cost,
            "batch_cost_usd": batch_cost,
            "cache_storage_cost_usd": storage_cost,
        },
        "notes": [
            "response.usage_metadata는 token 수를 주고, 최종 청구 금액 자체를 주지는 않아요.",
            "prompt caching hit token은 usage_metadata.cached_content_token_count로 확인해요.",
            "batch는 비동기 처리라 실시간 고객 응대가 아니라 평가/분류/리포트에 맞아요.",
        ],
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Day 2 cost projection",
        "",
        "| item | value |",
        "|---|---:|",
        f"| profile | `{result['profile']}` |",
        f"| model | `{result['model_id']}` |",
        f"| monthly requests | {result['monthly_requests']:,} |",
        f"| input tokens/request | {result['input_tokens_per_request']:,} |",
        f"| visible output tokens/request | {result['visible_output_tokens_per_request']:,} |",
        f"| thinking tokens/request | {result['thinking_tokens_per_request']:,} |",
        f"| cache hit rate | {result['cache_hit_rate']:.0%} |",
        f"| batch ratio | {result['batch_ratio']:.0%} |",
        f"| no optimization | ${result['no_optimization_cost_usd']:.4f} |",
        f"| optimized | ${result['optimized_cost_usd']:.4f} |",
        f"| savings | ${result['savings_usd']:.4f} ({result['savings_pct']}%) |",
        "",
        "## Cost breakdown",
        "",
        "```json",
        json.dumps(result["cost_breakdown"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in result["notes"])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="캐싱과 배치 비율을 반영해 월간 비용 추정")
    parser.add_argument("--report", default="day2/reports/cost_latest.json", help="cost_lab 리포트의 token 수 사용")
    parser.add_argument("--profile", choices=profile_names(), default=None, help="리포트의 profile 대신 사용할 profile")
    parser.add_argument("--daily-requests", type=int, default=3000)
    parser.add_argument("--business-days", type=int, default=22)
    parser.add_argument("--input-tokens", type=int, default=None)
    parser.add_argument("--visible-output-tokens", type=int, default=None)
    parser.add_argument("--thinking-tokens", type=int, default=None)
    parser.add_argument("--cache-hit-rate", type=float, default=0.0)
    parser.add_argument("--cacheable-input-ratio", type=float, default=0.6)
    parser.add_argument("--batch-ratio", type=float, default=0.0)
    parser.add_argument("--cache-storage-hours", type=float, default=24.0)
    parser.add_argument("--out-dir", default="day2/reports")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    row = _tokens_from_report(args.report) if Path(args.report).exists() else {}
    profile_name = args.profile or row.get("profile") or "cheap"
    result = project_cost(
        profile_name=profile_name,
        monthly_requests=args.daily_requests * args.business_days,
        input_tokens=args.input_tokens if args.input_tokens is not None else int(row.get("input_tokens") or 400),
        visible_output_tokens=args.visible_output_tokens if args.visible_output_tokens is not None else int(row.get("visible_output_tokens") or 300),
        thinking_tokens=args.thinking_tokens if args.thinking_tokens is not None else int(row.get("thinking_tokens") or 0),
        cache_hit_rate=max(0.0, min(1.0, args.cache_hit_rate)),
        cacheable_input_ratio=max(0.0, min(1.0, args.cacheable_input_ratio)),
        batch_ratio=max(0.0, min(1.0, args.batch_ratio)),
        cache_storage_hours=args.cache_storage_hours,
    )

    out_dir = Path(args.out_dir)
    write_json(out_dir / "cost_projection_latest.json", result)
    write_markdown(out_dir / "cost_projection_latest.md", render_markdown(result))

    print("\n=== Day 2 Cost Projection ===")
    print(f"profile={result['profile']} model={result['model_id']}")
    print(f"monthly_requests={result['monthly_requests']:,}")
    print(f"no_optimization=${result['no_optimization_cost_usd']:.4f}")
    print(f"optimized=${result['optimized_cost_usd']:.4f}")
    print(f"savings=${result['savings_usd']:.4f} ({result['savings_pct']}%)")
    print("breakdown=", json.dumps(result["cost_breakdown"], ensure_ascii=False))
    print(f"\nwrote {out_dir / 'cost_projection_latest.md'}")
    print(f"wrote {out_dir / 'cost_projection_latest.json'}")


if __name__ == "__main__":
    main()
