"""NPC pre-hook — validates invoke_npc calls before dispatching to npc_director."""

from __future__ import annotations

from uuid import uuid4

from app.ai.router import GameplayConfig
from app.core.npc_resolver import resolve_npc
from app.core.npc_scaffold import create_npc_record
from app.models.npc_fields import NpcFieldDef
from app.models.psychology import PsychologyDef


def validate_or_create_npc(
    name: str,
    world_state: dict,
    config: GameplayConfig,
    psychology: PsychologyDef | None = None,
    npc_fields: list[NpcFieldDef] | None = None,
) -> tuple[bool, str]:
    """Return (should_proceed, error_for_llm).

    Resolves by name (F2), gates on lifecycle only (A2), checks location match.
    Auto-creates if missing and configured.
    """
    resolution = resolve_npc(name, world_state)

    if resolution.npc_id is not None:
        npc = world_state["npcs"][resolution.npc_id]
        current_loc = world_state.get("meta", {}).get("current_location")
        npc_loc = npc.get("location")
        if current_loc and npc_loc and current_loc != npc_loc:
            # Locations are node UUIDs (ADR 0008 J3) — no place name available here.
            return False, f"{name} is elsewhere and is not present here."
        return True, ""

    if resolution.candidates or "not a known NPC" not in resolution.error:
        # Ambiguous, or matched only dead/removed NPCs — never auto-create over it.
        return False, resolution.error

    if not config.auto_create_npcs:
        return False, f"{name} is not a known NPC."

    world_state.setdefault("npcs", {})[str(uuid4())] = create_npc_record(
        name,
        detail=config.npc_auto_create_detail,
        psychology=psychology,
        npc_fields=npc_fields,
    )
    return True, ""
