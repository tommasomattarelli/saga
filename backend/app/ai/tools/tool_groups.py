"""Dynamic tool group resolver — filters active tools based on world state.

Groups and their activation conditions are defined in saga.config.yaml.
Predicates are typed Python functions; no eval() used.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.config_loader import load_saga_config

if TYPE_CHECKING:
    pass

# Predicates operating on the raw world_state dict (used in LangGraph nodes)
_STATE_PREDICATES: dict[str, Callable[[dict], bool]] = {
    "npcs_present": lambda ws: bool(ws.get("npcs")),
    "companion_active": lambda ws: bool(ws.get("companions")),
}


def resolve_active_tools_from_state(world_state: dict) -> set[str]:
    """Return the set of tool names active given a raw world_state dict.

    Used inside LangGraph nodes for per-step tool re-resolution after state mutations.
    """
    config = load_saga_config()
    groups: dict = config.get("tool_groups", {})

    active: set[str] = set()
    for group_def in groups.values():
        tools: list[str] = group_def.get("tools", [])
        if group_def.get("always"):
            active.update(tools)
            continue
        when: str | None = group_def.get("when")
        if when:
            predicate = _STATE_PREDICATES.get(when)
            if predicate and predicate(world_state):
                active.update(tools)

    return active
