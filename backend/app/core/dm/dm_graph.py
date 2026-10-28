"""LangGraph DM agent graph — wiring and routing only.

Graph structure:
    START
      └─► context_node          builds prompt, routes model
            └─► dm_node          calls LLM (non-streaming)
                  ├─► tools_node (if tool_calls present)
                  │     └─► dm_node  (loop back if meaningful tools ran)
                  │     └─► post_process_node (otherwise)
                  └─► post_process_node (if no tool_calls)
                        └─► END
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.core.dm.dm_helpers import last_ai_message, tool_calls_from_ai_message
from app.core.dm.dm_nodes import context_node, dm_node, post_process_node
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import dm_call_limit, needs_followup


def route_after_dm(state: GameState) -> Literal["tools_node", "post_process_node"]:
    ai_msg = last_ai_message(state["messages"])
    if ai_msg and tool_calls_from_ai_message(ai_msg):
        return "tools_node"
    return "post_process_node"


def route_after_tools(state: GameState) -> Literal["dm_node", "post_process_node"]:
    if state["step_count"] >= dm_call_limit(state) or state.get("closing_step", False):
        return "post_process_node"

    ai_msg = last_ai_message(state["messages"])
    if not ai_msg:
        return "post_process_node"

    tool_names = {tc["name"] for tc in tool_calls_from_ai_message(ai_msg)}
    followup = state.get("followup_required", needs_followup(tool_names))
    has_narration = bool(state["narration"].strip())

    if followup:
        return "dm_node"
    if has_narration:
        return "post_process_node"
    return "dm_node"


def build_dm_graph() -> Any:
    builder: StateGraph = StateGraph(GameState)

    builder.add_node("context_node", context_node)
    builder.add_node("dm_node", dm_node)
    builder.add_node("tools_node", tools_node)
    builder.add_node("post_process_node", post_process_node)

    builder.set_entry_point("context_node")
    builder.add_edge("context_node", "dm_node")
    builder.add_conditional_edges("dm_node", route_after_dm)
    builder.add_conditional_edges("tools_node", route_after_tools)
    builder.add_edge("post_process_node", END)

    return builder.compile()


dm_graph = build_dm_graph()
