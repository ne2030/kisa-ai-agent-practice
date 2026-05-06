"""Small Gemini/mock client used by the Day 2 labs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from day2.model_catalog import ModelProfile

load_dotenv()


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    model_id: str


def rough_token_count(text: str) -> int:
    # Good enough for workshop comparison. Live mode uses provider token counts.
    return max(1, len(text) // 3)


def _response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return text.strip()
    chunks: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                chunks.append(part_text)
    return "\n".join(chunks).strip()


def _usage(response: Any, prompt: str, text: str) -> tuple[int, int, int]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        input_tokens = rough_token_count(prompt)
        output_tokens = rough_token_count(text)
        return input_tokens, output_tokens, input_tokens + output_tokens
    input_tokens = int(getattr(usage, "prompt_token_count", None) or 0)
    output_text_tokens = int(getattr(usage, "candidates_token_count", None) or 0)
    reasoning_tokens = int(getattr(usage, "thoughts_token_count", None) or 0)
    output_tokens = output_text_tokens + reasoning_tokens
    total_tokens = int(getattr(usage, "total_token_count", None) or 0) or input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def generate_live(prompt: str, profile: ModelProfile, *, temperature: float = 0.2, max_output_tokens: int = 900) -> LLMResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for live mode. Use --llm-mode mock for offline practice.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    started = time.perf_counter()
    response = client.models.generate_content(
        model=profile.model_id,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=max_output_tokens),
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    text = _response_text(response)
    input_tokens, output_tokens, total_tokens = _usage(response, prompt, text)
    return LLMResult(text, input_tokens, output_tokens, total_tokens, latency_ms, profile.model_id)


def generate_mock(prompt: str, profile: ModelProfile, *, purpose: str = "cost") -> LLMResult:
    started = time.perf_counter()
    if purpose == "cost":
        if profile.name == "cheap":
            text = """1. 송장 API 지연으로 일부 주문 출고와 배송 문의가 늘었어요.\n2. 반품은 14일 이내라 접수 가능성이 높아요.\n3. VIP 배송 지연 보상은 쿠폰 검토 대상이에요.\n다음 조치: 송장 정상화 후 지연 주문을 우선 확인해요."""
        elif profile.name == "strong":
            text = """1. 핵심 요약 3줄\n- 오전 송장 API 지연이 주문 출고 문의와 배송 지연 문의를 만들었어요.\n- ORD-1001은 결제/재고가 확인됐지만 물류센터 W-2 송장 생성이 늦어졌어요.\n- 러닝화 반품과 VIP 보상은 각각 기간/등급 조건 확인 후 처리할 수 있어요.\n2. 고객 영향: 선물 일정, 반품 기대, 지연 보상 기대가 동시에 발생했어요.\n3. 원인 후보: 송장 API 지연과 물류센터 처리 대기예요.\n4. 다음 조치: 14:00 정상화 뒤 ORD-1001 송장 생성 여부를 확인하고, 반품은 회수 검수 안내, VIP 보상은 5,000원 한도로 검토해요.\n5. 확실하지 않은 내용: 상품 훼손 여부와 일반 고객 보상 가능성은 추가 확인이 필요해요."""
        else:
            text = """1. 핵심 요약 3줄\n- 송장 API 지연 때문에 출고/배송 문의가 늘었어요.\n- 반품 요청은 14일 이내라 접수 가능하지만 회수 후 상태 확인이 필요해요.\n- VIP 고객의 3일 배송 지연은 최대 5,000원 쿠폰 기준에 들어갈 수 있어요.\n2. 고객 영향: 선물 일정 지연, 반품 처리 기대, 보상 문의가 발생했어요.\n3. 원인 후보: 물류센터 송장 생성 지연과 오전 송장 API 장애예요.\n4. 바로 할 다음 조치: 14:00 정상화 후 송장 생성 확인, 반품 접수 안내, VIP 여부 확인 후 보상 처리예요.\n5. 확실하지 않은 내용: 상품 훼손 여부와 일반 고객 보상 여부는 추가 확인이 필요해요."""
    else:
        text = "mock response"

    latency_hint = {"cheap": 120.0, "standard": 260.0, "strong": 620.0}.get(profile.name, 250.0)
    actual_ms = (time.perf_counter() - started) * 1000
    input_tokens = rough_token_count(prompt)
    output_tokens = rough_token_count(text)
    return LLMResult(text, input_tokens, output_tokens, input_tokens + output_tokens, round(latency_hint + actual_ms, 2), f"mock:{profile.name}")


def generate_text(prompt: str, profile: ModelProfile, *, llm_mode: str, purpose: str = "cost", temperature: float = 0.2, max_output_tokens: int = 900) -> LLMResult:
    if llm_mode == "mock":
        return generate_mock(prompt, profile, purpose=purpose)
    return generate_live(prompt, profile, temperature=temperature, max_output_tokens=max_output_tokens)
