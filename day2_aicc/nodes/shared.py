"""Small helpers shared by Day 2 graph nodes."""

from __future__ import annotations

from typing import Any

from day2_aicc.state import AICCState, ToolCall


def trace_tool(state: AICCState, name: str, args: dict[str, Any], result: dict[str, Any]) -> list[ToolCall]:
    """Append one tool call to the state trace without mutating the input state."""
    return [*state.get("tool_trace", []), {"name": name, "args": args, "result": result}]


def append_risk_event(state: AICCState, event: str) -> list[str]:
    """Append one readable event for terminal output and eval reports."""
    return [*state.get("risk_events", []), event]
