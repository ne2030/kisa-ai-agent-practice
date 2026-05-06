"""Action and final response nodes."""

from __future__ import annotations

from typing import Any

from day2_aicc.model_policy import estimate_cost
from day2_aicc.nodes.shared import append_risk_event
from day2_aicc.state import AICCState, ToolCall
from day2_aicc.tools import TOOL_REGISTRY


def execute_action_node(state: AICCState) -> dict[str, Any]:
    """Run approved write tools after `action_guard`."""
    if state.get("blocked"):
        return {"risk_events": append_risk_event(state, "execute_action:skipped_blocked")}

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
        "risk_events": append_risk_event(state, f"execute_action:executed={len(executed)}"),
    }


def final_review_node(state: AICCState) -> dict[str, Any]:
    """Build the final answer and attach the workshop cost estimate."""
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
        "risk_events": append_risk_event(state, "final_review:done"),
    }
