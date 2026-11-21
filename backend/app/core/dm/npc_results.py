from app.ai.npc_outcomes import NPCInteraction
from app.ai.router import get_gameplay_config
from app.core.dm.npc_context import NPCBeat
from app.core.dm.operation_recorder import OperationRecorder
from app.memory.operation_delta import OperationState
from app.memory.operation_results import MessageResult
from app.memory.updater import apply_typed_updates


def apply_actor_effects(
    npc_id: str,
    result: NPCInteraction,
    world_state: dict,
    char_data: dict,
    baseline: dict,
) -> tuple[dict, dict]:
    update: dict = {
        "key": "npc_psychology",
        "target": npc_id,
        "changes": dict(result.axis_changes),
    }
    psychology = (baseline.get("taxonomy") or {}).get("psychology")
    if psychology:
        update["config"] = psychology
    return apply_typed_updates(world_state, char_data, [update])


def flush_interaction_history(
    world_state: dict,
    beats: list[NPCBeat],
    operations: OperationRecorder | None = None,
    *,
    step: int | None = None,
) -> None:
    entries: dict[str, list[str]] = {}
    for beat in beats:
        for result in beat.results:
            parts = [*(f'"{line}"' for line in result.lines)]
            if result.action:
                parts.append(result.action)
            entries.setdefault(result.npc_id, []).append(" ".join(parts) or "[silent]")
    kept = get_gameplay_config().npc_last_interactions_kept
    for npc_id, interactions in entries.items():
        npc = world_state.get("npcs", {}).get(npc_id)
        if npc is not None:
            before = OperationState.capture(world_state, {}, {})
            history = [*npc.get("last_interactions", []), "\n".join(interactions)]
            npc["last_interactions"] = history[-kept:] if kept > 0 else []
            if operations is not None:
                operations.append(
                    origin="finalization",
                    name="record_interactions",
                    arguments={"npc_id": npc_id},
                    outcome="succeeded",
                    step=step,
                    before=before,
                    after=OperationState.capture(world_state, {}, {}),
                    result=MessageResult(description="Stored NPC interaction history."),
                )
