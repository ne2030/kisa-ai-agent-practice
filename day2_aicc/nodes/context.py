"""Context nodes: load trusted business data and policy docs."""

from __future__ import annotations

from typing import Any

from day2_aicc.guardrails import block
from day2_aicc.model_policy import resolve_policy
from day2_aicc.nodes.shared import append_risk_event, trace_tool
from day2_aicc.state import AICCState
from day2_aicc.tools import get_customer, get_order, get_shipment, retrieve_policy


def load_context_node(state: AICCState) -> dict[str, Any]:
    """Load order/customer/shipment with read-only tools.

    This is also the data boundary: the order must belong to `state.user_id`.
    """
    order_id = state.get("order_id", "")
    if not order_id:
        return block(state, reason="order_id missing", layer="context_loader")

    order_result = get_order(order_id)
    trace = trace_tool(state, "get_order", {"order_id": order_id}, order_result)
    if not order_result.get("ok"):
        return {**block(state, reason=order_result.get("error", "order lookup failed"), layer="context_loader"), "tool_trace": trace}

    order = order_result["order"]
    if order.get("customer_id") != state.get("user_id"):
        # TODO-D2-02: 실제 서비스라면 auth token의 subject와 order owner를 비교한다.
        return {
            **block(state, reason="order does not belong to current customer", layer="data_boundary"),
            "order": order,
            "tool_trace": trace,
        }

    customer_result = get_customer(order["customer_id"])
    trace = [*trace, {"name": "get_customer", "args": {"customer_id": order["customer_id"]}, "result": customer_result}]
    shipment_result = get_shipment(order_id)
    trace = [*trace, {"name": "get_shipment", "args": {"order_id": order_id}, "result": shipment_result}]

    if not customer_result.get("ok") or not shipment_result.get("ok"):
        return {**block(state, reason="customer or shipment lookup failed", layer="context_loader"), "tool_trace": trace}

    return {
        "order": order,
        "customer": customer_result["customer"],
        "shipment": shipment_result["shipment"],
        "tool_trace": trace,
        "risk_events": append_risk_event(state, "context_loader:passed"),
    }


def retrieve_policy_node(state: AICCState) -> dict[str, Any]:
    """Retrieve policy docs for the specialist.

    Indirect injection enters through this node when `attack_mode=indirect`.
    """
    policy = resolve_policy(state.get("model_policy"))
    max_docs = policy.max_policy_docs
    if state.get("budget_mode") == "strict":
        max_docs = min(max_docs, 1)

    result = retrieve_policy(
        state.get("intent", "unknown"),
        include_poisoned=state.get("attack_mode") == "indirect",
        max_docs=max_docs,
    )
    # TODO-D2-03: strict budget에서 max_docs를 줄이면 비용은 줄지만 policy 누락 가능성이 커진다.
    return {
        "policy_docs": result.get("policy_docs", []),
        "tool_trace": trace_tool(
            state,
            "retrieve_policy",
            {"intent": state.get("intent"), "include_poisoned": state.get("attack_mode") == "indirect", "max_docs": max_docs},
            result,
        ),
        "risk_events": append_risk_event(state, f"retrieve_policy:docs={len(result.get('policy_docs', []))}"),
    }
