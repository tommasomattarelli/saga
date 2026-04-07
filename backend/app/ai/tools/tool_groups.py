"""Dynamic tool group resolver — filters active tools based on world state.

Groups and their activation conditions are defined in saga.config.yaml.
Predicates are typed Python functions; no eval() used.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.config_loader import load_saga_config

if TYPE_CHECKING:
    from app.models.campaign import Campaign

_PREDICATES: dict[str, Callable[[Campaign], bool]] = {
    "combat_active": lambda c: bool(
        c.world_state.get("combat_state", {}).get("active")
    ),
    "npcs_present": lambda c: bool(c.world_state.get("npcs")),
    "companion_active": lambda c: bool(c.world_state.get("companions")),
}


def resolve_active_tools(campaign: "Campaign") -> set[str]:
    """Return the set of tool names active for this turn."""
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
            predicate = _PREDICATES.get(when)
            if predicate and predicate(campaign):
                active.update(tools)

    return active
