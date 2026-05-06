"""Model profiles and workshop cost estimates for Day 2 cost lab."""

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
    expected_style: str


MODEL_PROFILES: dict[str, ModelProfile] = {
    "cheap": ModelProfile(
        name="cheap",
        label="cheap / fast",
        model_id=os.getenv("DAY2_MODEL_CHEAP", "gemini-2.5-flash-lite"),
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.40,
        expected_style="짧고 빠르지만 누락이 생길 수 있는 요약",
    ),
    "standard": ModelProfile(
        name="standard",
        label="standard / balanced",
        model_id=os.getenv("DAY2_MODEL_STANDARD", "gemini-2.5-flash"),
        input_usd_per_1m=0.30,
        output_usd_per_1m=2.50,
        expected_style="구조와 세부사항의 균형이 좋은 요약",
    ),
    "strong": ModelProfile(
        name="strong",
        label="strong / careful",
        model_id=os.getenv("DAY2_MODEL_STRONG", "gemini-2.5-pro"),
        input_usd_per_1m=1.25,
        output_usd_per_1m=10.00,
        expected_style="비싸지만 원인/리스크/다음 조치를 더 꼼꼼히 분리하는 요약",
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


def estimate_cost_usd(profile: ModelProfile, input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1_000_000) * profile.input_usd_per_1m
    output_cost = (output_tokens / 1_000_000) * profile.output_usd_per_1m
    return round(input_cost + output_cost, 8)
