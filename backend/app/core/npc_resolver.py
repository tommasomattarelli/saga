"""ADR 0009 F2 — the single NPC name→UUID resolver.

Scans the overlay (`world_state["npcs"]`) over each record's `slug` + `name`;
living matches shadow dead/removed ones. Shares only the reject-with-candidates
shape with the 0008 place resolver — different index, different data source.
Candidate labels are enriched with place names in the tool layer, not here.
"""

from dataclasses import dataclass, field


@dataclass
class NpcResolution:
    npc_id: str | None = None
    error: str = ""  # LLM-readable (std 13); empty on success
    candidates: list[str] = field(default_factory=list)  # npc UUIDs on ambiguity


def resolve_npc(name: str, world_state: dict, *, include_gone: bool = False) -> NpcResolution:
    wanted = name.strip().casefold()
    living: list[str] = []
    gone: list[tuple[str, str]] = []  # (npc_id, lifecycle)

    for npc_id, npc in world_state.get("npcs", {}).items():
        aliases = {str(npc.get("name", "")).casefold(), str(npc.get("slug") or "").casefold()}
        if wanted not in aliases - {""}:
            continue
        lifecycle = npc.get("lifecycle", "alive")
        if lifecycle == "alive":
            living.append(npc_id)
        else:
            gone.append((npc_id, lifecycle))

    pool = living if living or not include_gone else [npc_id for npc_id, _ in gone]
    if len(pool) == 1:
        return NpcResolution(npc_id=pool[0])
    if len(pool) > 1:
        return NpcResolution(
            error=f"Multiple NPCs match '{name}' — specify which one.",
            candidates=pool,
        )
    if gone:
        return NpcResolution(error=f"{name} is {gone[0][1]} and cannot act.")
    return NpcResolution(error=f"{name} is not a known NPC.")


def npcs_at_current_location(world_state: dict) -> dict[str, dict]:
    """Living NPCs at the current location, keyed by uuid (ADR 0009 F1/A5)."""
    current_location = world_state.get("meta", {}).get("current_location", "")
    return {
        npc_id: data
        for npc_id, data in world_state.get("npcs", {}).items()
        if data.get("lifecycle", "alive") == "alive"
        and (not current_location or data.get("location") == current_location)
    }
