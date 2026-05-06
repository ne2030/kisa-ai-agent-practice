"""LangGraph wiring for the Day 2 AICC/e-commerce agent.

Read this file first. It only answers one question: "what order do the nodes
run in?" Node behavior lives in `day2_aicc/nodes/` so students can open one
small file at a time.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from langgraph.graph import END, START, StateGraph

from day2_aicc.guardrails import action_guard_node, input_guard_node, sanitize_policy_docs
from day2_aicc.nodes import (
    blocked_or_continue,
    execute_action_node,
    final_review_node,
    load_context_node,
    retrieve_policy_node,
    specialist_node,
    triage_node,
)
from day2_aicc.state import AICCState

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise RuntimeError(
        "Day 2 uses LangGraph SQLite checkpoints. Install with: "
        "pip install langgraph langgraph-checkpoint-sqlite"
    ) from exc

DEFAULT_CHECKPOINT_DB = Path(__file__).resolve().parent / "checkpoints" / "day2.sqlite"


GRAPH_NODE_ORDER = [
    "input_guard",
    "triage",
    "load_context",
    "retrieve_policy",
    "context_guard",
    "specialist",
    "action_guard",
    "execute_action",
    "final_review",
]


def build_graph(checkpointer: Any | None = None):
    """Build the Day 2 workflow.

    Only `specialist` is the LLM-agent node. The other nodes are host-side
    routing, guardrail, context, tool, or response steps.
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
