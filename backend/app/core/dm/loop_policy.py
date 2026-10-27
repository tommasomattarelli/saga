from app.ai.router import get_gameplay_config
from app.ai.tools.dm_tools import get_tool
from app.ai.tools.tool_groups import resolve_active_tools_from_state
from app.core.dm.game_state import GameState


def dm_call_limit(state: GameState) -> int:
    return (
        state["max_agent_steps"]
        if "max_agent_steps" in state
        else get_gameplay_config().max_agent_steps
    )


def recursion_limit(dm_calls: int) -> int:
    # Context + N × (DM + tools) + post-process, with one superstep to terminate.
    return 2 * dm_calls + 3


def closing_step(state: GameState) -> bool:
    return (
        state["step_count"] >= dm_call_limit(state) - 1
        or state.get("consecutive_empty_steps", 0)
        >= get_gameplay_config().consecutive_empty_steps_max
    )


def step_tools(world_state: dict, *, closing: bool) -> set[str]:
    active = resolve_active_tools_from_state(world_state)
    if not closing:
        return active
    return {name for name in active if (tool := get_tool(name)) is not None and tool.terminal_safe}


def needs_followup(names: set[str]) -> bool:
    return any((tool := get_tool(name)) is None or not tool.terminal_safe for name in names)
