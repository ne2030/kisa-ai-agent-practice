"""Model routing and cost estimation helpers for the Day 2 practice.

Model profiles map business routing names to price/quality assumptions.

Day 2 now uses a live Gemini call by default; these profiles still provide local
cost estimates, prompt-caching/batch math, and the optional `--llm-mode mock`
path used for deterministic graph debugging.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from day2_aicc.state import AICCState, CostBreakdown, IntentName, ModelPolicyName


@dataclass(frozen=True)
class ModelPolicy:
    name: ModelPolicyName
    label: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    cached_input_discount: float
    batch_discount: float
    quality_baseline: int
    max_policy_docs: int
    notes: str


MODEL_POLICIES: dict[str, ModelPolicy] = {
    "cheap": ModelPolicy(
        name="cheap",
        label="cheap / fast router",
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.40,
        cached_input_discount=0.75,
        batch_discount=0.50,
        quality_baseline=62,
        max_policy_docs=1,
        notes="낮은 비용. mock mode에서는 긴 정책 충돌, 예외 조건, injection 분리에서 취약한 profile로 둔다.",
    ),
    "standard": ModelPolicy(
        name="standard",
        label="standard / default agent",
        input_usd_per_1m=0.30,
        output_usd_per_1m=2.50,
        cached_input_discount=0.75,
        batch_discount=0.50,
        quality_baseline=78,
        max_policy_docs=2,
        notes="기본 실습 정책. 일반 업무는 충분하지만 위험 action은 guardrail 보조가 필요하다.",
    ),
    "strong": ModelPolicy(
        name="strong",
        label="strong / escalation",
        input_usd_per_1m=1.25,
        output_usd_per_1m=10.00,
        cached_input_discount=0.75,
        batch_discount=0.50,
        quality_baseline=90,
        max_policy_docs=3,
        notes="높은 비용. mock mode에서는 모호한 취소/환불, 공격성 context, 보상 판단에서 더 보수적인 profile로 둔다.",
    ),
}


def resolve_policy(name: str | None) -> ModelPolicy:
    if not name:
        return MODEL_POLICIES["standard"]
    return MODEL_POLICIES.get(name, MODEL_POLICIES["standard"])


def route_model_for_intent(intent: IntentName, budget_mode: str = "normal") -> ModelPolicyName:
    """Simple routing policy used by the graph.

    TODO-D2-06: 비용 실습 확장 지점.
    - strict budget일 때는 조회성 intent를 cheap으로 보내고
    - 환불/보상/action intent는 standard 이상으로 올리는 정책을 직접 바꿔본다.
    - 변경 후 `python3 day2_aicc/eval_day2.py --compare-models`로 품질/비용 차이를 확인한다.
    """
    if budget_mode == "strict" and intent in {"order_status", "delivery_status"}:
        return "cheap"
    if intent in {"cancel_or_refund", "compensation"}:
        return "standard"
    return "standard"


def rough_token_count(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    # Korean tokenization varies by model. A workshop-safe estimate is enough here.
    return max(1, len(text) // 3)


def estimate_cost(state: AICCState, *, batch: bool = False) -> CostBreakdown:
    policy = resolve_policy(state.get("model_policy"))
    stable_prompt_tokens = 900  # system prompt + tool schemas: good prompt caching candidate
    request_tokens = rough_token_count(
        {
            "message": state.get("message", ""),
            "customer": state.get("customer", {}),
            "order": state.get("order", {}),
            "shipment": state.get("shipment", {}),
            "policy_docs": state.get("sanitized_policy_docs") or state.get("policy_docs", []),
        }
    )
    output_tokens = rough_token_count(state.get("answer_draft") or state.get("final_answer") or "") + 80

    cached_tokens = stable_prompt_tokens
    uncached_tokens = request_tokens
    batch_multiplier = policy.batch_discount if batch else 1.0

    input_usd = (uncached_tokens / 1_000_000) * policy.input_usd_per_1m
    cached_input_usd = (cached_tokens / 1_000_000) * policy.input_usd_per_1m * (1 - policy.cached_input_discount)
    output_usd = (output_tokens / 1_000_000) * policy.output_usd_per_1m
    total = (input_usd + cached_input_usd + output_usd) * batch_multiplier

    return {
        "input_tokens": uncached_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "input_usd": round(input_usd, 8),
        "cached_input_usd": round(cached_input_usd, 8),
        "output_usd": round(output_usd, 8),
        "batch_multiplier": batch_multiplier,
        "total_usd": round(total, 8),
    }


def quality_baseline(policy_name: str | None) -> int:
    return resolve_policy(policy_name).quality_baseline
