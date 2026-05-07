"""2일차 실습에서 쓰는 모델 호출 코드예요."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from day2.model_catalog import ModelProfile

load_dotenv()


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    visible_output_tokens: int
    thinking_tokens: int
    cached_input_tokens: int
    total_tokens: int
    latency_ms: float
    model_id: str
    finish_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def output_tokens(self) -> int:
        return self.visible_output_tokens + self.thinking_tokens


def rough_token_count(text: str) -> int:
    # 실습용 대략치예요. 실제 호출에서는 제공자가 반환한 토큰 수를 사용해요.
    return max(1, len(text) // 3)


def _response_text(response: Any) -> str:
    chunks: list[str] = []

    direct_text = getattr(response, "text", None)
    if direct_text:
        chunks.append(str(direct_text))

    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text and str(part_text) not in chunks:
                chunks.append(str(part_text))

    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def _finish_reason(response: Any) -> str:
    for candidate in getattr(response, "candidates", []) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is None:
            continue
        name = getattr(reason, "name", None)
        return str(name or reason)
    return ""


def _usage(response: Any, prompt: str, text: str) -> tuple[int, int, int, int, int]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        input_tokens = rough_token_count(prompt)
        visible_tokens = rough_token_count(text)
        return input_tokens, visible_tokens, 0, 0, input_tokens + visible_tokens

    input_tokens = int(getattr(usage, "prompt_token_count", None) or 0)
    visible_tokens = int(getattr(usage, "candidates_token_count", None) or 0)
    thinking_tokens = int(getattr(usage, "thoughts_token_count", None) or 0)
    cached_tokens = int(getattr(usage, "cached_content_token_count", None) or 0)
    total_tokens = int(getattr(usage, "total_token_count", None) or 0) or input_tokens + visible_tokens + thinking_tokens
    return input_tokens, visible_tokens, thinking_tokens, cached_tokens, total_tokens


def _warnings(text: str, visible_tokens: int, thinking_tokens: int, finish_reason: str, max_output_tokens: int) -> list[str]:
    warnings: list[str] = []
    if finish_reason == "MAX_TOKENS":
        warnings.append(
            f"finish_reason=MAX_TOKENS: max_output_tokens={max_output_tokens} 안에서 thinking/output이 잘렸을 수 있어요."
        )
    if not text and (visible_tokens or thinking_tokens):
        warnings.append("usage token은 있는데 visible text가 없어요. thinking token이 예산을 먹었거나 응답 파싱을 확인해야 해요.")
    if thinking_tokens and visible_tokens < 80:
        warnings.append("thinking token 대비 visible output이 짧아요. thinking_budget이나 max_output_tokens를 조정해요.")
    return warnings


def _generate_config(types: Any, profile: ModelProfile, temperature: float, max_output_tokens: int) -> Any:
    kwargs: dict[str, Any] = {"temperature": temperature, "max_output_tokens": max_output_tokens}
    thinking_cls = getattr(types, "ThinkingConfig", None)
    if thinking_cls is not None and profile.default_thinking_budget is not None:
        kwargs["thinking_config"] = thinking_cls(thinking_budget=profile.default_thinking_budget)
    try:
        return types.GenerateContentConfig(**kwargs)
    except TypeError:
        kwargs.pop("thinking_config", None)
        return types.GenerateContentConfig(**kwargs)


def generate_live(prompt: str, profile: ModelProfile, *, temperature: float = 0.2, max_output_tokens: int = 2048) -> LLMResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for live mode. Use --llm-mode mock for offline practice.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config = _generate_config(types, profile, temperature, max_output_tokens)

    started = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=profile.model_id,
            contents=prompt,
            config=config,
        )
    except Exception as exc:  # 실습 중 명령줄 에러가 길게 터지지 않게 정리해요.
        message = str(exc)
        if "API key expired" in message or "API_KEY_INVALID" in message:
            raise RuntimeError("Gemini live call failed: API key가 만료됐어요. 새 key를 .env에 넣거나 --llm-mode mock으로 실행해요.") from exc
        if "quota" in message.lower() or "RESOURCE_EXHAUSTED" in message:
            raise RuntimeError("Gemini live call failed: quota/rate limit에 걸렸어요. 잠시 뒤 다시 실행하거나 --llm-mode mock을 써요.") from exc
        raise
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    text = _response_text(response)
    input_tokens, visible_tokens, thinking_tokens, cached_tokens, total_tokens = _usage(response, prompt, text)
    finish_reason = _finish_reason(response)
    return LLMResult(
        text=text,
        input_tokens=input_tokens,
        visible_output_tokens=visible_tokens,
        thinking_tokens=thinking_tokens,
        cached_input_tokens=cached_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        model_id=profile.model_id,
        finish_reason=finish_reason,
        warnings=_warnings(text, visible_tokens, thinking_tokens, finish_reason, max_output_tokens),
    )


def _mock_cost_text(profile: ModelProfile, prompt: str) -> str:
    is_naive = "아래 내용을 요약해줘" in prompt
    is_concise = "3개 bullet" in prompt
    is_json = "JSON만 출력" in prompt
    is_latest_status = "latest-status-wins" in prompt or "ORD-4219" in prompt
    is_refund = "반품 가능성 판단" in prompt or ("반품 가능 기간" in prompt and "러닝화" in prompt and "VIP" not in prompt)
    is_vip = "배송 지연 보상" in prompt and "VIP" in prompt and "러닝화" not in prompt

    if is_latest_status:
        if is_naive:
            return "ORD-4219은 송장 생성 이후라 배송지 변경이 불가해요. 고객에게 현재 배송 단계라 변경이 어렵다고 안내해야 해요."
        return """1. 핵심 요약 3줄
- ORD-4219는 최신 물류 상태가 IN_TRANSIT이에요.
- 09:25 LABEL_CREATED 이후 배송지 변경은 불가해요.
- 09:43 PICKED_UP 이후라 출고 보류도 어렵게 봐야 해요.
2. 고객 영향: 고객이 요청한 배송지 변경 처리가 어려워요.
3. 원인 후보: 09:10 상담 메모와 이후 물류 이벤트 사이에 시간 차이가 있었어요.
4. 바로 할 다음 조치: 최신 상태 기준으로 배송지 변경 불가를 안내해요.
5. 확실하지 않은 내용: 고객이 상담사에게 출고 전이라고 들은 정확한 시각은 확인이 필요해요."""

    if is_json:
        return '{"summary":["송장 API 지연으로 일부 주문 출고가 늦어졌어요","반품은 14일 이내 접수 가능하지만 훼손 여부 확인이 필요해요","VIP 배송 지연 보상은 최대 5,000원 쿠폰 검토 대상이에요"],"customer_impact":["선물 일정 지연","반품 처리 기대","보상 문의"],"cause_candidates":["물류센터 W-2 송장 생성 지연","오전 송장 API 지연"],"next_actions":["14:00 정상화 후 송장 생성 확인","반품 회수 후 훼손 여부 확인","VIP 등급과 실제 지연일 확인"],"unknowns":["상품 훼손 여부","일반 고객 보상 여부"]}'

    if is_naive:
        if profile.name == "strong":
            return "송장 API 지연으로 주문 출고와 배송 문의가 늘었고, 반품과 배송 지연 보상 문의도 함께 들어왔어요. 물류센터 W-2와 14:00 정상화 예정, 반품 14일 조건, VIP 최대 5,000원 쿠폰 기준을 확인해 후속 안내가 필요해요."
        return "배송 지연, 반품, 보상 쿠폰 문의가 함께 들어왔어요. 송장 API 지연이 주요 원인으로 보이고, 고객별로 배송 상황과 반품 가능 여부를 확인해 안내해야 해요."

    if is_refund:
        return "기간상 14일 이내라 반품 접수는 가능해 보여요. 다만 최종 승인은 회수 후 상품 훼손 여부를 확인해야 해요. 실외 착용 흔적이 있으면 거절될 수 있어요."
    if is_vip:
        return "VIP 고객이고 3일 지연이라 2일 이상 조건에 들어가 최대 5,000원 쿠폰 검토 대상이에요. 지급 전 실제 배송 완료일과 고객 등급을 확인해야 해요."
    if is_concise or profile.name == "cheap":
        return """- 송장 API 지연으로 ORD-1001 출고와 배송 문의가 늘었고 14:00 정상화 후 확인이 필요해요.
- 러닝화 반품은 14일 이내라 접수 가능하지만 회수 후 훼손 여부 확인이 필요해요.
- VIP 3일 배송 지연은 최대 5,000원 쿠폰 검토 대상이지만 지급 전 조건 확인이 필요해요."""
    if profile.name == "strong":
        return """1. 핵심 요약 3줄
- 오전 송장 API 지연이 주문 출고 문의와 배송 지연 문의를 만들었어요.
- ORD-1001은 결제/재고가 확인됐지만 물류센터 W-2 송장 생성이 늦어졌어요.
- 러닝화 반품은 14일 이내 접수 가능하고, VIP 보상은 등급 조건 확인 후 처리할 수 있어요.
2. 고객 영향: 선물 일정, 반품 기대, 지연 보상 기대가 동시에 발생했어요.
3. 원인 후보: 송장 API 지연과 물류센터 W-2 처리 대기예요.
4. 다음 조치: 14:00 정상화 뒤 ORD-1001 송장 생성 여부를 확인하고, 반품은 회수 검수 안내, VIP 보상은 5,000원 한도로 검토해요.
5. 확실하지 않은 내용: 상품 훼손 여부와 일반 고객 보상 가능성은 추가 확인이 필요해요."""
    return """1. 핵심 요약 3줄
- 송장 API 지연 때문에 출고/배송 문의가 늘었어요.
- 반품 요청은 14일 이내라 접수 가능하지만 회수 후 상태 확인이 필요해요.
- VIP 고객의 3일 배송 지연은 최대 5,000원 쿠폰 기준에 들어갈 수 있어요.
2. 고객 영향: 선물 일정 지연, 반품 처리 기대, 보상 문의가 발생했어요.
3. 원인 후보: 물류센터 W-2 송장 생성 지연과 오전 송장 API 장애예요.
4. 바로 할 다음 조치: 14:00 정상화 후 송장 생성 확인, 반품 접수 안내, VIP 여부 확인 후 보상 처리예요.
5. 확실하지 않은 내용: 상품 훼손 여부와 일반 고객 보상 여부는 추가 확인이 필요해요."""


def generate_mock(prompt: str, profile: ModelProfile, *, purpose: str = "cost") -> LLMResult:
    started = time.perf_counter()
    text = _mock_cost_text(profile, prompt) if purpose == "cost" else "mock response"

    latency_hint = {"cheap": 120.0, "standard": 260.0, "strong": 620.0}.get(profile.name, 250.0)
    actual_ms = (time.perf_counter() - started) * 1000
    input_tokens = rough_token_count(prompt)
    visible_tokens = rough_token_count(text)
    thinking_tokens = 0 if profile.name != "strong" else 128
    return LLMResult(
        text=text,
        input_tokens=input_tokens,
        visible_output_tokens=visible_tokens,
        thinking_tokens=thinking_tokens,
        cached_input_tokens=0,
        total_tokens=input_tokens + visible_tokens + thinking_tokens,
        latency_ms=round(latency_hint + actual_ms, 2),
        model_id=f"mock:{profile.name}",
        finish_reason="STOP",
        warnings=[],
    )


def generate_text(
    prompt: str,
    profile: ModelProfile,
    *,
    llm_mode: str,
    purpose: str = "cost",
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
) -> LLMResult:
    if llm_mode == "mock":
        return generate_mock(prompt, profile, purpose=purpose)
    return generate_live(prompt, profile, temperature=temperature, max_output_tokens=max_output_tokens)
