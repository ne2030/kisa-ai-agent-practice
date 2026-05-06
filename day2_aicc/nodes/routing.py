"""Routing node: classify the request before context loading.

This file is intentionally lightweight. `triage` is not an agent in this lab;
it is a deterministic router that fills `intent`, `order_id`, and model policy.
"""

from __future__ import annotations

import re
from typing import Any

from day2_aicc.model_policy import route_model_for_intent
from day2_aicc.nodes.shared import append_risk_event
from day2_aicc.state import AICCState, IntentName


def extract_order_id(message: str) -> str:
    match = re.search(r"ORD-\d+", message, re.I)
    return match.group(0).upper() if match else ""


def extract_address(message: str) -> str:
    match = re.search(r"배송지(?:를|를)?\s+(.+?)(?:로|으로)\s*(?:바꿔|변경)", message)
    if match:
        return match.group(1).strip()
    marker = "주소:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return ""


def parse_intent(message: str) -> IntentName:
    lowered = message.lower()
    if any(k in message for k in ["배송지", "주소 변경"]):
        return "address_change"
    if any(k in message for k in ["환불", "반품", "취소"]):
        return "cancel_or_refund"
    if any(k in message for k in ["보상", "쿠폰", "지연"]):
        return "compensation"
    # TODO-D2-01: 교환/분실/부분 취소 같은 intent를 하나 더 추가하고 graph/eval까지 연결한다.
    if any(k in message for k in ["배송", "송장", "택배"]):
        return "delivery_status"
    if "order" in lowered or "주문" in message:
        return "order_status"
    return "unknown"


def blocked_or_continue(state: AICCState) -> str:
    return "blocked" if state.get("blocked") else "continue"


def triage_node(state: AICCState) -> dict[str, Any]:
    message = state.get("message", "")
    intent = parse_intent(message)
    selected_policy = state.get("model_policy") or "standard"
    if selected_policy == "auto":
        selected_policy = route_model_for_intent(intent, state.get("budget_mode", "normal"))

    return {
        "intent": intent,
        "order_id": extract_order_id(message),
        "requested_address": extract_address(message),
        "model_policy": selected_policy,
        "risk_events": append_risk_event(state, f"triage:{intent}:model={selected_policy}"),
    }
