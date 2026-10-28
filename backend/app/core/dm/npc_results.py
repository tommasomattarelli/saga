from app.ai.npc_director import NPCDialogue
from app.ai.router import get_gameplay_config
from app.core.dm.dm_helpers import get_or_create_segment
from app.core.npc_resolver import resolve_npc
from app.memory.updater import apply_typed_updates


def _handle_npc_results(
    npc_name: str,
    npc_results: list[NPCDialogue],
    npc_dialogues: list[dict],
    narration_segments: list[dict],
    step: int,
    world_state: dict,
    char_data: dict,
    baseline: dict | None = None,
) -> tuple[str, dict, dict]:
    dialogue_parts: list[str] = []
    kept = get_gameplay_config().npc_last_interactions_kept
    for npc in npc_results:
        evt = {"npc_name": npc.npc_name, "dialogue": npc.dialogue, "action": npc.action}
        npc_dialogues.append(evt)
        seg = get_or_create_segment(narration_segments, step)
        seg["npc_dialogues"].append(evt)
        part = f'{npc.npc_name}: "{npc.dialogue}"'
        if npc.action:
            part += f" [{npc.action}]"
        dialogue_parts.append(part)
        resolution = resolve_npc(npc.npc_name, world_state)
        if resolution.npc_id is not None:
            npc_ws = world_state["npcs"][resolution.npc_id]
            history: list[str] = npc_ws.setdefault("last_interactions", [])
            history.append(f'"{npc.dialogue}"')
            if len(history) > kept:
                history[:] = history[-kept:]
        # PR 1 preserves conversation effects; typed failures are ADR 0017 (PR 2).
        update: dict = {
            "key": "npc_psychology",
            "target": resolution.npc_id or npc.npc_name,
            "changes": dict(npc.axis_changes),
        }
        psychology_config = ((baseline or {}).get("taxonomy") or {}).get("psychology")
        if psychology_config:
            update["config"] = psychology_config
        world_state, char_data = apply_typed_updates(world_state, char_data, [update])
    result_str = " | ".join(dialogue_parts) if dialogue_parts else f"{npc_name} does not respond."
    return result_str, world_state, char_data
