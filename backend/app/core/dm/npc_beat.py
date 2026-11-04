import copy
import json
import uuid
from collections import Counter

from langchain_core.messages import ToolMessage

from app.ai.npc_director import NPCInput, invoke_npcs_parallel
from app.ai.npc_outcomes import NPCFailure
from app.ai.router import get_gameplay_config
from app.core.dm.dialogue_composition import NPCLine, public_name, register_lines
from app.core.dm.game_state import GameState
from app.core.dm.npc_context import NPCBeat, PublicNPCResult, visible_actor_context
from app.core.dm.npc_prehook import prepare_npc_calls
from app.core.dm.npc_results import apply_actor_effects
from app.core.dm.progress import StepProgress
from app.core.npc_resolver import npcs_at_current_location
from app.core.psychology import resolve_psychology


async def execute_npc_beat(
    state: GameState,
    calls: list[dict],
    world_state: dict,
    char_data: dict,
    beats: list[NPCBeat],
    registry: list[NPCLine],
    progress: StepProgress,
) -> tuple[dict, dict, list[ToolMessage]]:
    config = get_gameplay_config()
    baseline = state.get("world_baseline") or {}
    selected, notes = prepare_npc_calls(calls, world_state, config, baseline)
    location = world_state.get("meta", {}).get("current_location", "")
    observers = frozenset(npcs_at_current_location(world_state))
    step = state["step_count"] - 1
    actors = []
    for candidate in selected:
        profile = copy.deepcopy(world_state["npcs"][candidate.npc_id])
        node = baseline.get("nodes", {}).get(profile.get("location") or "", {})
        profile["location_name"] = node.get("name")
        narration, observed = visible_actor_context(
            candidate.npc_id,
            state.get("narrative_observations", []),
            beats,
        )
        actors.append(
            NPCInput(
                npc_name=candidate.name,
                npc_id=candidate.npc_id,
                step=step,
                beat=len(beats),
                npc_profile=profile,
                player_action=state["player_action"],
                invocation_context=candidate.context,
                dm_narration=narration,
                observed_beats=observed,
                scene_context=json.dumps(
                    {
                        "location": node.get("name"),
                        "condition": profile.get("condition"),
                        "hp": profile.get("hp"),
                        "player": {
                            k: copy.deepcopy(char_data.get(k)) for k in ("name", "hp", "inventory")
                        },
                    },
                    ensure_ascii=False,
                ),
                psychology=resolve_psychology(baseline.get("taxonomy")),
                fill_empty_traits=config.npc_auto_create_detail == "rich",
                language=state["prompt_context"].language if state.get("prompt_context") else "en",
            )
        )
    results = await invoke_npcs_parallel(actors, uuid.UUID(state["user_id"])) if actors else []
    public = []
    counts = Counter(
        str(n.get("name", "")).casefold() for n in world_state.get("npcs", {}).values()
    )
    ambiguous = {name for name, count in counts.items() if count > 1}
    for candidate, result in zip(selected, results, strict=True):
        args = {"npc_id": candidate.npc_id, "context": candidate.context}
        if isinstance(result, NPCFailure):
            notes[candidate.call_index] = result.note
            progress.record("invoke_npc", args, result.note)
            continue
        world_state, char_data = apply_actor_effects(
            candidate.npc_id,
            result,
            world_state,
            char_data,
            baseline,
        )
        event = PublicNPCResult(
            candidate.npc_id, public_name(candidate.name), result.lines, result.action
        )
        public.append(event)
        lines = register_lines(
            registry,
            candidate.npc_id,
            candidate.name,
            result.lines,
            step=step,
            beat=len(beats),
            ambiguous_names=ambiguous,
        )
        note = "\n".join(f"{line.handle} {line.part.dialogue}" for line in lines)
        if not lines:
            note = f"{event.npc_name} intentionally remains silent."
        if result.action:
            note += f"\nDescriptive action/intention: {result.action}"
        notes[candidate.call_index] = note
        progress.record(
            "invoke_npc", args, {"lines": result.lines, "action": result.action}, playable=True
        )
    beats.append(NPCBeat(step, observers, location, tuple(public)))
    messages = [
        ToolMessage(
            content=notes[index],
            tool_call_id=call.get("id", "invoke_npc"),
            name="invoke_npc",
        )
        for index, call in enumerate(calls)
    ]
    return world_state, char_data, messages
