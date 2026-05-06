"""Model profiles and workshop cost estimates for Day 2 cost lab.

The numbers mirror the public Gemini Developer API pricing page enough for
classroom estimation. Always verify provider pricing before production use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    label: str
    model_id: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    batch_input_usd_per_1m: float
    batch_output_usd_per_1m: float
    cache_read_usd_per_1m: float
    cache_storage_usd_per_1m_hour: float
    expected_style: str
    default_thinking_budget: int | None = None


MODEL_PROFILES: dict[str, ModelProfile] = {
    "cheap": ModelProfile(
        name="cheap",
        label="cheap / fast",
        model_id=os.getenv("DAY2_MODEL_CHEAP", "gemini-2.5-flash-lite"),
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.40,
        batch_input_usd_per_1m=0.05,
        batch_output_usd_per_1m=0.20,
        cache_read_usd_per_1m=0.01,
        cache_storage_usd_per_1m_hour=1.00,
        expected_style="짧고 빠르지만 누락이 생길 수 있는 요약",
        default_thinking_budget=0,
    ),
    "standard": ModelProfile(
        name="standard",
        label="standard / balanced",
        model_id=os.getenv("DAY2_MODEL_STANDARD", "gemini-2.5-flash"),
        input_usd_per_1m=0.30,
        output_usd_per_1m=2.50,
        batch_input_usd_per_1m=0.15,
        batch_output_usd_per_1m=1.25,
        cache_read_usd_per_1m=0.03,
        cache_storage_usd_per_1m_hour=1.00,
        expected_style="구조와 세부사항의 균형이 좋은 요약",
        default_thinking_budget=0,
    ),
    "strong": ModelProfile(
        name="strong",
        label="strong / careful",
        model_id=os.getenv("DAY2_MODEL_STRONG", "gemini-2.5-pro"),
        input_usd_per_1m=1.25,
        output_usd_per_1m=10.00,
        batch_input_usd_per_1m=0.625,
        batch_output_usd_per_1m=5.00,
        cache_read_usd_per_1m=0.125,
        cache_storage_usd_per_1m_hour=4.50,
        expected_style="비싸지만 원인/리스크/다음 조치를 더 꼼꼼히 분리하는 요약",
        # Gemini 2.5 Pro는 thinking off가 안 돼요. 낮은 budget으로 실습 출력 토큰을 확보해요.
        default_thinking_budget=128,
    ),
}


def get_profile(name: str) -> ModelProfile:
    try:
        return MODEL_PROFILES[name]
    except KeyError as exc:
        names = ", ".join(MODEL_PROFILES)
        raise ValueError(f"unknown model profile: {name}. choose one of: {names}") from exc


def profile_names() -> list[str]:
    return list(MODEL_PROFILES)


def estimate_cost_usd(
    profile: ModelProfile,
    input_tokens: int,
    output_tokens: int,
    *,
    cached_input_tokens: int = 0,
    batch: bool = False,
    cache_storage_tokens: int = 0,
    cache_storage_hours: float = 0,
) -> float:
    """Estimate request cost from token counts.

    output_tokens should already include visible output + thinking tokens.
    cached_input_tokens means cache-hit input tokens charged at cache read price.
    """

    cached_input_tokens = max(0, min(cached_input_tokens, input_tokens))
    fresh_input_tokens = max(0, input_tokens - cached_input_tokens)

    input_rate = profile.batch_input_usd_per_1m if batch else profile.input_usd_per_1m
    output_rate = profile.batch_output_usd_per_1m if batch else profile.output_usd_per_1m

    input_cost = (fresh_input_tokens / 1_000_000) * input_rate
    cached_input_cost = (cached_input_tokens / 1_000_000) * profile.cache_read_usd_per_1m
    output_cost = (output_tokens / 1_000_000) * output_rate
    storage_cost = (cache_storage_tokens / 1_000_000) * profile.cache_storage_usd_per_1m_hour * cache_storage_hours
    return round(input_cost + cached_input_cost + output_cost + storage_cost, 8)
