"""LangGraph workflow for the Day 2 AICC/e-commerce agent.

The important LangGraph idea in this file:

1. `StateGraph(AICCState)` says every node reads and writes the same state shape.
2. Each node function receives the current state and returns only the fields it
   wants to update.
3. `build_graph()` connects the node names with edges. The node names printed in
   `risk_events` are the same names used here.
4. `open_compiled_graph()` adds a SQLite checkpointer, so a `thread_id` can pause
   after one node and resume from the next node.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from langgraph.graph import END, START, StateGraph

from day2_aicc.guardrails import action_guard_node, block, input_guard_node, sanitize_policy_docs
from day2_aicc.mock_data import TODAY
from day2_aicc.model_policy import estimate_cost, resolve_policy, route_model_for_intent
from day2_aicc.state import AICCState, IntentName, ProposedAction, ToolCall
from day2_aicc.tools import (
    TOOL_REGISTRY,
    get_customer,
    get_order,
    get_shipment,
    retrieve_policy,
)

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise RuntimeError(
        "Day 2 uses LangGraph SQLite checkpoints. Install with: "
        "pip install langgraph langgraph-checkpoint-sqlite"
    ) from exc

DEFAULT_CHECKPOINT_DB = Path(__file__).resolve().parent / "checkpoints" / "day2.sqlite"


def _trace(state: AICCState, name: str, args: dict[str, Any], result: dict[str, Any]) -> list[ToolCall]:
    return [*state.get("tool_trace", []), {"name": name, "args": args, "result": result}]


def _risk(state: AICCState, event: str) -> list[str]:
    return [*state.get("risk_events", []), event]


def _extract_order_id(message: str) -> str:
    match = re.search(r"ORD-\d+", message, re.I)
    return match.group(0).upper() if match else ""


def _extract_address(message: str) -> str:
    match = re.search(r"배송지(?:를|를)?\s+(.+?)(?:로|으로)\s*(?:바꿔|변경)", message)
    if match:
        return match.group(1).strip()
    # Fallback for the instructor to type custom messages quickly.
    marker = "주소:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return ""


def _parse_intent(message: str) -> IntentName:
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
    """Classify the request before any business action is considered.

    This is deliberately simple string matching so the lab can focus on graph
    structure. In a production service this could be a cheap classifier model.
    """
    message = state.get("message", "")
    intent = _parse_intent(message)
    selected_policy = state.get("model_policy") or "standard"
    if selected_policy == "auto":
        selected_policy = route_model_for_intent(intent, state.get("budget_mode", "normal"))

    return {
        "intent": intent,
        "order_id": _extract_order_id(message),
        "requested_address": _extract_address(message),
        "model_policy": selected_policy,
        "risk_events": _risk(state, f"triage:{intent}:model={selected_policy}"),
    }


def load_context_node(state: AICCState) -> dict[str, Any]:
    """Load trusted business context with read-only tools.

    This node is also the data-boundary checkpoint: even if the user mentions a
    valid order ID, the order must belong to the current `user_id`.
    """
    order_id = state.get("order_id", "")
    if not order_id:
        return block(state, reason="order_id missing", layer="context_loader")

    order_result = get_order(order_id)
    trace = _trace(state, "get_order", {"order_id": order_id}, order_result)
    if not order_result.get("ok"):
        return {**block(state, reason=order_result.get("error", "order lookup failed"), layer="context_loader"), "tool_trace": trace}

    order = order_result["order"]
    if order.get("customer_id") != state.get("user_id"):
        # TODO-D2-02: 실제 서비스라면 auth token의 subject와 order owner를 비교한다.
        # 실습에서는 user_id fixture만 사용하므로, 실패 케이스를 하나 추가해 data boundary를 확인한다.
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
        "risk_events": _risk(state, "context_loader:passed"),
    }


def retrieve_policy_node(state: AICCState) -> dict[str, Any]:
    """Retrieve policy documents that the specialist will read.

    The indirect-injection scenario appends an external poisoned document here.
    That makes the threat concrete: the user did not type the attack, but the
    model may still see it through retrieved context.
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
    # eval report에 max_docs 변경 전/후 결과를 비교하는 열을 추가한다.
    return {
        "policy_docs": result.get("policy_docs", []),
        "tool_trace": _trace(
            state,
            "retrieve_policy",
            {"intent": state.get("intent"), "include_poisoned": state.get("attack_mode") == "indirect", "max_docs": max_docs},
            result,
        ),
        "risk_events": _risk(state, f"retrieve_policy:docs={len(result.get('policy_docs', []))}"),
    }


def _doc_text(state: AICCState) -> str:
    docs = state.get("sanitized_policy_docs") or state.get("policy_docs", [])
    return "\n".join(doc.get("text", "") for doc in docs)


def _days_since_delivery(order: dict[str, Any]) -> int | None:
    if not order.get("delivered_date"):
        return None
    from datetime import date

    return (TODAY - date.fromisoformat(order["delivered_date"])).days


def mock_specialist_node(state: AICCState) -> dict[str, Any]:
    """Draft a response and propose tool actions.

    This node intentionally simulates quality differences between model policies.
    Cheap can propose risky actions that later guardrails must catch.
    """
    intent = state.get("intent", "unknown")
    order = state.get("order", {})
    shipment = state.get("shipment", {})
    customer = state.get("customer", {})
    policy_name = state.get("model_policy", "standard")
    docs_text = _doc_text(state)
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
        age = _days_since_delivery(order)
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
        # approve_coupon 같은 human-in-the-loop node를 graph에 추가해 본다.
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
        "risk_events": _risk(state, f"specialist:mock:actions={len(actions)}"),
    }


def specialist_node(state: AICCState) -> dict[str, Any]:
    """Choose between deterministic mock behavior and the live Gemini call."""
    if state.get("llm_mode", "live") == "mock":
        return mock_specialist_node(state)
    try:
        from .live_llm import live_specialist_node
    except ImportError:  # pragma: no cover
        from day2_aicc.live_llm import live_specialist_node

    return live_specialist_node(state)


def execute_action_node(state: AICCState) -> dict[str, Any]:
    """Run approved write tools.

    All risky business changes should arrive here only after `action_guard`.
    Keeping execution in one node makes it easy to audit what actually happened.
    """
    if state.get("blocked"):
        return {"risk_events": _risk(state, "execute_action:skipped_blocked")}

    executed: list[ToolCall] = []
    trace = state.get("tool_trace", [])
    for action in state.get("proposed_actions", []):
        tool_name = action.get("tool")
        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            result = {"ok": False, "error": f"unknown tool: {tool_name}"}
        else:
            result = tool(**action.get("args", {}))
        call: ToolCall = {"name": tool_name or "unknown", "args": action.get("args", {}), "result": result}
        executed.append(call)
        trace = [*trace, call]

    return {
        "executed_actions": [*state.get("executed_actions", []), *executed],
        "tool_trace": trace,
        "risk_events": _risk(state, f"execute_action:executed={len(executed)}"),
    }


def final_review_node(state: AICCState) -> dict[str, Any]:
    """Build the final customer-facing answer and attach a cost estimate."""
    if state.get("blocked"):
        final = (
            "요청을 그대로 처리할 수 없습니다. "
            f"사유: {state.get('block_reason', 'safety policy')} "
            "주문 상태와 정책 기준 안에서 가능한 대안을 안내드릴게요."
        )
    elif state.get("executed_actions"):
        events = [call["result"].get("event", call["name"]) for call in state.get("executed_actions", [])]
        final = f"{state.get('answer_draft', '')} 처리 결과: {', '.join(events)}."
    else:
        final = state.get("answer_draft", "확인된 정보 기준으로 안내할 내용이 없습니다.")

    synthetic_state = {**state, "final_answer": final}
    cost = estimate_cost(synthetic_state)
    if state.get("live_model"):
        cost["live_model"] = state.get("live_model")  # type: ignore[typeddict-unknown-key]
    if state.get("llm_usage"):
        for key, value in state["llm_usage"].items():
            cost[f"live_{key}"] = value  # type: ignore[typeddict-unknown-key]

    return {
        "final_answer": final,
        "cost": cost,
        "risk_events": _risk(state, "final_review:done"),
    }


def build_graph(checkpointer: Any | None = None):
    """Wire the workflow.

    Read this function first when LangGraph feels abstract. The graph is not
    hidden inside the framework; it is this list of named nodes and edges.
    """
    builder = StateGraph(AICCState)
    builder.add_node("input_guard", input_guard_node)
    builder.add_node("triage", triage_node)
    builder.add_node("load_context", load_context_node)
    builder.add_node("retrieve_policy", retrieve_policy_node)
    builder.add_node("context_guard", sanitize_policy_docs)
    builder.add_node("specialist", specialist_node)
    builder.add_node("action_guard", action_guard_node)
    builder.add_node("execute_action", execute_action_node)
    builder.add_node("final_review", final_review_node)

    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges("input_guard", blocked_or_continue, {"blocked": "final_review", "continue": "triage"})
    builder.add_edge("triage", "load_context")
    builder.add_conditional_edges("load_context", blocked_or_continue, {"blocked": "final_review", "continue": "retrieve_policy"})
    builder.add_edge("retrieve_policy", "context_guard")
    builder.add_edge("context_guard", "specialist")
    builder.add_edge("specialist", "action_guard")
    builder.add_conditional_edges("action_guard", blocked_or_continue, {"blocked": "final_review", "continue": "execute_action"})
    builder.add_edge("execute_action", "final_review")
    builder.add_edge("final_review", END)

    return builder.compile(checkpointer=checkpointer)


@contextmanager
def open_compiled_graph(db_path: str | Path = DEFAULT_CHECKPOINT_DB) -> Iterator[Any]:
    path = Path(db_path)
    if str(db_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        yield build_graph(checkpointer=checkpointer)


def thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}
