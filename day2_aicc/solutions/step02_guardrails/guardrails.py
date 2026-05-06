"""Guardrail layers for the Day 2 practice.

The implementation is intentionally readable and partly TODO-driven. Students can
add cases without needing a full policy engine.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from .mock_data import TODAY
from .state import AICCState, GuardLayer, ProposedAction

DIRECT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous",
    r"system\s+prompt",
    r"developer\s+mode",
    r"bypass\s+(the\s+)?guard",
    r"tool\s*schema",
    r"reveal\s+(customer|phone|email|secret)",
    r"이전\s*(지시|규칙|명령).*(무시|잊어)",
    r"(시스템|개발자)\s*프롬프트",
    r"(가드레일|보안정책)\s*(우회|무시|해제)",
    r"관리자\s*모드",
]

INDIRECT_INJECTION_PATTERNS = [
    r"system\s+override",
    r"ignore\s+(all\s+)?previous",
    r"call\s+issue_coupon",
    r"mark\s+guardrails\s+as\s+passed",
    r"reveal\s+customer",
    r"<!--.*-->",
    r"data:text/plain;base64",
    r"base64",
    r"\[[^\]]+\]\(javascript:",
]


def guard_enabled(state: AICCState, layer: GuardLayer) -> bool:
    mode = (state.get("guard_mode") or "on").strip().lower()
    if mode == "off":
        return False
    if mode == "on":
        return True
    enabled = {part.strip() for part in mode.split(",") if part.strip()}
    return layer in enabled


def append_event(state: AICCState, event: str) -> list[str]:
    return [*state.get("risk_events", []), event]


def block(state: AICCState, *, reason: str, layer: str) -> dict[str, Any]:
    return {
        "blocked": True,
        "block_reason": reason,
        "blocked_by": layer,
        "risk_events": append_event(state, f"blocked:{layer}:{reason}"),
    }


def input_guard_node(state: AICCState) -> dict[str, Any]:
    if not guard_enabled(state, "input"):
        return {"risk_events": append_event(state, "input_guard:skipped")}

    message = state.get("message", "")
    matched = [pattern for pattern in DIRECT_INJECTION_PATTERNS if re.search(pattern, message, re.I)]
    if matched:
        return block(
            state,
            reason=f"direct prompt injection pattern detected: {matched[0]}",
            layer="input_guard",
        )
    return {"risk_events": append_event(state, "input_guard:passed")}


def sanitize_policy_docs(state: AICCState) -> dict[str, Any]:
    docs = state.get("policy_docs", [])
    if not guard_enabled(state, "context"):
        return {
            "sanitized_policy_docs": docs,
            "context_flags": [],
            "risk_events": append_event(state, "context_guard:skipped"),
        }

    sanitized: list[dict[str, Any]] = []
    flags: list[str] = []
    for doc in docs:
        text = doc.get("text", "")
        matched = [pattern for pattern in INDIRECT_INJECTION_PATTERNS if re.search(pattern, text, re.I)]
        untrusted = doc.get("trust") != "internal"
        if matched or untrusted:
            flags.append(f"{doc.get('doc_id')}:untrusted_or_instruction_like")
            # Keep metadata only so the final answer can say that a suspicious external doc was ignored.
            sanitized.append(
                {
                    "doc_id": doc.get("doc_id"),
                    "source": doc.get("source"),
                    "trust": doc.get("trust", "unknown"),
                    "title": doc.get("title"),
                    "text": "[removed by context guard: external instruction-like payload]",
                }
            )
        else:
            sanitized.append(doc)

    event = "context_guard:flagged" if flags else "context_guard:passed"
    return {
        "sanitized_policy_docs": sanitized,
        "context_flags": flags,
        "risk_events": append_event(state, event),
    }


def delivered_age_days(order: dict[str, Any]) -> int | None:
    delivered = order.get("delivered_date")
    if not delivered:
        return None
    delivered_date = date.fromisoformat(delivered)
    return (TODAY - delivered_date).days


def validate_action(state: AICCState, action: ProposedAction) -> str | None:
    """Return a denial reason, or None when the action is allowed."""
    order = state.get("order", {})
    shipment = state.get("shipment", {})
    customer = state.get("customer", {})
    tool = action.get("tool")
    args = action.get("args", {})

    if state.get("context_flags") and action.get("risk") in {"medium", "high"}:
        return "suspicious external context cannot authorize risky actions"

    if tool == "update_shipping_address":
        if order.get("status") != "processing":
            return "shipping address can only be changed before shipment"
        if shipment.get("tracking_no"):
            return "shipping address cannot change after tracking number is assigned"
        if not args.get("new_address"):
            return "new address is missing"

    if tool == "cancel_order":
        if order.get("status") != "processing":
            return "order cancellation is only allowed while processing"

    if tool == "create_return_request":
        age = delivered_age_days(order)
        if order.get("status") != "delivered":
            return "return request requires delivered order"
        if age is None or age > 14:
            return "return window exceeded 14 days"

    if tool == "issue_coupon":
        amount = int(args.get("amount_krw", 0))
        if customer.get("tier") != "vip":
            return "coupon requires VIP manual policy path"
        if int(shipment.get("delayed_days", 0)) < 2:
            return "coupon requires delivery delay of at least 2 days"
        if amount > 5000:
            return "coupon amount exceeds 5,000 KRW policy limit"

    return None


def action_guard_node(state: AICCState) -> dict[str, Any]:
    actions = state.get("proposed_actions", [])
    if not actions:
        return {"risk_events": append_event(state, "action_guard:no_action")}

    if not guard_enabled(state, "action"):
        return {"risk_events": append_event(state, "action_guard:skipped")}

    for action in actions:
        denial = validate_action(state, action)
        if denial:
            return block(state, reason=f"{action.get('tool')}: {denial}", layer="action_guard")

    return {"risk_events": append_event(state, "action_guard:passed")}
