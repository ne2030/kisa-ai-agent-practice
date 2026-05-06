"""Specialist node: the only LLM-agent node in the Day 2 graph."""

from __future__ import annotations

from datetime import date
from typing import Any

from day2_aicc.mock_data import TODAY
from day2_aicc.nodes.shared import append_risk_event
from day2_aicc.state import AICCState, ProposedAction


def policy_doc_text(state: AICCState) -> str:
    docs = state.get("sanitized_policy_docs") or state.get("policy_docs", [])
    return "\n".join(doc.get("text", "") for doc in docs)


def days_since_delivery(order: dict[str, Any]) -> int | None:
    if not order.get("delivered_date"):
        return None
    return (TODAY - date.fromisoformat(order["delivered_date"])).days


def mock_specialist_node(state: AICCState) -> dict[str, Any]:
    """Deterministic specialist used for structure and regression checks.

    Cheap/standard/strong are simulated profiles here so model-cost and guardrail
    behavior can be demonstrated without making a live LLM call.
    """
    intent = state.get("intent", "unknown")
    order = state.get("order", {})
    shipment = state.get("shipment", {})
    customer = state.get("customer", {})
    policy_name = state.get("model_policy", "standard")
    docs_text = policy_doc_text(state)
    actions: list[ProposedAction] = []
    notes: list[str] = []

    if policy_name == "cheap":
        notes.append("cheap profile: lower policy reasoning fidelity")
    elif policy_name == "strong":
        notes.append("strong profile: escalated reasoning for policy edge cases")

    if intent == "order_status":
        draft = f"{order['order_id']} 상태는 {order['status']}이고 결제는 완료되어 있습니다. 품목은 {', '.join(order['items'])}입니다."

    elif intent == "delivery_status":
        draft = (
            f"{order['order_id']} 배송 상태는 {shipment['delivery_status']}입니다. "
            f"택배사는 {shipment.get('carrier') or '아직 배정 전'}, 송장번호는 {shipment.get('tracking_no') or '아직 없음'}, "
            f"예상 도착일은 {shipment['eta']}입니다."
        )

    elif intent == "address_change":
        new_address = state.get("requested_address") or "서울시 종로구 사직로 9"
        # TODO-D2-04: cheap profile이 shipped 주문에도 action을 제안하는 문제를 수정한 뒤,
        # action_guard가 없어도 안전해지는지 guards=off로 비교한다.
        if policy_name == "cheap" or order.get("status") == "processing":
            actions.append(
                {
                    "tool": "update_shipping_address",
                    "args": {"order_id": order["order_id"], "new_address": new_address},
                    "reason": "customer requested shipping address change",
                    "risk": "medium",
                }
            )
            draft = f"배송지를 {new_address}로 변경 처리하겠습니다."
        else:
            draft = "이미 출고된 주문이라 배송지 직접 변경은 어렵습니다. 택배사 문의 또는 반송 후 재주문 절차를 안내드릴게요."

    elif intent == "cancel_or_refund":
        age = days_since_delivery(order)
        if order.get("status") == "processing":
            actions.append(
                {
                    "tool": "cancel_order",
                    "args": {"order_id": order["order_id"]},
                    "reason": "processing order cancellation",
                    "risk": "high",
                }
            )
            draft = "출고 전 주문이라 취소와 환불을 바로 진행하겠습니다."
        elif order.get("status") == "delivered" and (policy_name == "cheap" or (age is not None and age <= 14)):
            actions.append(
                {
                    "tool": "create_return_request",
                    "args": {"order_id": order["order_id"], "reason": "customer refund request"},
                    "reason": "return/refund request",
                    "risk": "high",
                }
            )
            draft = "반품 접수를 생성하고 환불 절차를 안내드리겠습니다."
        else:
            draft = "배송 완료 후 14일이 지나 일반 환불 창구로는 처리하기 어렵습니다. 예외 사유가 있으면 상담 티켓으로 검토할 수 있습니다."

    elif intent == "compensation":
        # TODO-D2-05: compensation은 금전성 action이라 모델 판단만 믿기 어렵다.
        if policy_name == "cheap" and "issue_coupon" in docs_text:
            actions.append(
                {
                    "tool": "issue_coupon",
                    "args": {"customer_id": customer["customer_id"], "amount_krw": 50000, "reason": "external policy doc instruction"},
                    "reason": "followed external document instruction",
                    "risk": "high",
                }
            )
            draft = "외부 FAQ 지시에 따라 50,000원 쿠폰을 발급하겠습니다."
        elif customer.get("tier") == "vip" and int(shipment.get("delayed_days", 0)) >= 2:
            actions.append(
                {
                    "tool": "issue_coupon",
                    "args": {"customer_id": customer["customer_id"], "amount_krw": 5000, "reason": "delivery delay compensation"},
                    "reason": "VIP delivery delay compensation",
                    "risk": "medium",
                }
            )
            draft = "배송 지연 3일로 확인됩니다. VIP 보상 기준에 따라 5,000원 쿠폰을 처리하겠습니다."
        else:
            actions.append(
                {
                    "tool": "create_support_ticket",
                    "args": {"customer_id": customer["customer_id"], "order_id": order["order_id"], "reason": "delivery delay compensation review"},
                    "reason": "manual compensation review",
                    "risk": "low",
                }
            )
            draft = "자동 보상 기준에 바로 해당하지 않아 상담 티켓으로 검토하겠습니다."

    else:
        actions.append(
            {
                "tool": "create_support_ticket",
                "args": {"customer_id": customer.get("customer_id", state.get("user_id", "unknown")), "order_id": order.get("order_id", "unknown"), "reason": "unknown intent"},
                "reason": "fallback to human support",
                "risk": "low",
            }
        )
        draft = "요청 의도를 확정하기 어려워 상담 티켓으로 이어가겠습니다."

    return {
        "answer_draft": draft,
        "proposed_actions": actions,
        "quality_notes": [*state.get("quality_notes", []), *notes],
        "risk_events": append_risk_event(state, f"specialist:mock:actions={len(actions)}"),
    }


def specialist_node(state: AICCState) -> dict[str, Any]:
    """Dispatch to mock specialist or live Gemini specialist."""
    if state.get("llm_mode", "live") == "mock":
        return mock_specialist_node(state)
    try:
        from day2_aicc.live_llm import live_specialist_node
    except ImportError:  # pragma: no cover
        from ..live_llm import live_specialist_node

    return live_specialist_node(state)
