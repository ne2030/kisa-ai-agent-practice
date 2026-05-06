"""Shared state shape for the Day 2 LangGraph practice."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

GuardLayer = Literal["input", "context", "action"]
GuardMode = Literal["on", "off", "input", "context", "action"]
ModelPolicyName = Literal["cheap", "standard", "strong"]
LLMMode = Literal["live", "mock"]
IntentName = Literal[
    "order_status",
    "delivery_status",
    "address_change",
    "cancel_or_refund",
    "compensation",
    "unknown",
]


class ToolCall(TypedDict, total=False):
    name: str
    args: dict[str, Any]
    result: dict[str, Any]


class ProposedAction(TypedDict, total=False):
    tool: str
    args: dict[str, Any]
    reason: str
    risk: Literal["low", "medium", "high"]


class CostBreakdown(TypedDict, total=False):
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    input_usd: float
    cached_input_usd: float
    output_usd: float
    batch_multiplier: float
    total_usd: float


class AICCState(TypedDict, total=False):
    # Request / runtime options
    thread_id: str
    scenario: str
    user_id: str
    message: str
    model_policy: ModelPolicyName
    llm_mode: LLMMode
    guard_mode: str
    budget_mode: Literal["normal", "strict"]
    attack_mode: Literal["none", "direct", "indirect"]

    # Parsed / loaded context
    intent: IntentName
    order_id: str
    requested_address: str
    customer: dict[str, Any]
    order: dict[str, Any]
    shipment: dict[str, Any]
    policy_docs: list[dict[str, Any]]
    sanitized_policy_docs: list[dict[str, Any]]

    # Decisions / safety
    blocked: bool
    block_reason: str
    blocked_by: str
    context_flags: list[str]
    risk_events: list[str]
    proposed_actions: list[ProposedAction]
    executed_actions: list[ToolCall]
    tool_trace: list[ToolCall]

    # Output / metrics
    answer_draft: str
    final_answer: str
    cost: CostBreakdown
    live_model: str
    llm_usage: dict[str, int]
    llm_raw_response: str
    quality_notes: list[str]
    errors: list[str]
