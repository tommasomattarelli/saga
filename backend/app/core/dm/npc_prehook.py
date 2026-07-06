"""NPC pre-hook — validates invoke_npc calls before dispatching to npc_director."""

from __future__ import annotations

from app.ai.router import GameplayConfig


def validate_or_create_npc(
    name: str, world_state: dict, config: GameplayConfig
) -> tuple[bool, str]:
    """Return (should_proceed, error_for_llm).

    Checks presence, alive status, and location match. Auto-creates if missing and configured.
    """
    npcs = world_state.get("npcs", {})

    if name in npcs:
        npc = npcs[name]
        status = npc.get("status", "alive")
        if npc.get("is_dead") or status in ("dead", "removed"):
            return False, f"{name} is dead and cannot speak."

        current_loc = world_state.get("meta", {}).get("current_location")
        npc_loc = npc.get("location")
        if current_loc and npc_loc and current_loc != npc_loc:
            # Locations are node UUIDs (ADR 0008 J3) — no place name available here.
            return False, f"{name} is elsewhere and is not present here."

        return True, ""

    if not config.auto_create_npcs:
        return False, f"{name} is not a known NPC."

    world_state.setdefault("npcs", {})[name] = _create_npc_profile(
        name, config.npc_auto_create_detail
    )
    return True, ""


def _create_npc_profile(name: str, detail: str) -> dict:
    base: dict = {
        "name": name,
        "disposition_toward_player": 0,
        "last_interactions": [],
    }
    if detail == "minimal":
        return base
    standard = {
        **base,
        "role": "Commoner",
        "location": "",
        "personality": "unremarkable",
        "motivation": "survive",
    }
    if detail == "standard":
        return standard
    return {**standard, "secret": "None", "fear": "death"}
