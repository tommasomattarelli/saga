import copy
import uuid
from dataclasses import asdict

from app.ai.npc_director import NPCInput, invoke_npcs_parallel
from app.ai.npc_outcomes import NPCResult
from app.ai.prompts.dm import campaign_prompt_context
from app.ai.router import ModelConfig
from app.core.dialogue_markers import strip_markers
from app.core.dm.dm_graph import route_after_tools
from app.core.dm.dm_helpers import last_ai_message, raw_history_to_lc
from app.core.dm.dm_nodes import dm_node, post_process_node
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.models.quest import QuestRegistry
from eval.dialogue.cases import case_for_scenario_name
from eval.dialogue.metrics import ActorDispatch, pipeline_metrics
from eval.dialogue.requests import SuiteProvider
from eval.dialogue.runtime import pipeline_context
from eval.probes.probes import PROBES_BY_NAME, grade
from eval.scenario_tools.scenario import Scenario


def initial_state(sc: Scenario, user_id: uuid.UUID) -> GameState:
    return {
        "player_action": sc.stimuli["npc_speaks"].player,
        "campaign_id": "non-persisting-evaluation",
        "user_id": str(user_id),
        "messages": raw_history_to_lc(
            [
                *sc.history,
                {
                    "role": "user",
                    "content": sc.stimuli["npc_speaks"].player,
                },
            ]
        ),
        "world_state": copy.deepcopy(sc.campaign.world_state),
        "world_baseline": copy.deepcopy(sc.campaign.world_baseline),
        "char_data": copy.deepcopy(sc.campaign.character_data),
        "quests": QuestRegistry.model_validate(sc.campaign.quests),
        "difficulty": sc.campaign.difficulty,
        "narration": "",
        "narration_segments": [],
        "npc_beats": [],
        "npc_lines": [],
        "narrative_observations": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "dice_results": [],
        "time_passed_minutes": 0,
        "model_used": "",
        "importance_score": 5,
        "step_count": 0,
        "max_agent_steps": 3,
        "consecutive_empty_steps": 0,
        "progress_fingerprints": [],
        "allowed_tools": [],
        "closing_step": False,
        "followup_required": False,
        "death_event": None,
        "system_prompt": "",
        "prompt_context": campaign_prompt_context(
            sc.campaign,
            sc.summary_context,
            sc.global_summary,
            sc.recalled_memories("npc_speaks"),
        ),
        "model_config": {},
    }


def apply_update(state: GameState, result: dict) -> None:
    messages = result.pop("messages", [])
    state.update(result)
    state["messages"].extend(messages)


async def run_pipeline(
    sc: Scenario,
    trace: SuiteProvider,
    config: ModelConfig,
    user_id: uuid.UUID,
) -> tuple[dict, list[str]]:
    state = initial_state(sc, user_id)
    case = case_for_scenario_name(sc.name)
    before = copy.deepcopy(state["world_state"])
    responses = []
    dispatches: list[ActorDispatch] = []
    previous_attempts = {attempt.key for attempt in trace.ledger.results()}

    async def observe_actors(actors: list[NPCInput], owner: uuid.UUID) -> list[NPCResult]:
        selected = [
            ActorDispatch(
                actor.npc_id, actor.npc_name, actor.step, actor.beat, actor.observed_beats
            )
            for actor in actors
        ]
        dispatches.extend(selected)
        results = await invoke_npcs_parallel(actors, owner)
        for item, result in zip(selected, results, strict=True):
            item.status = result.status
        return results

    failed: list[str] = []
    with pipeline_context((trace, config), observe_actors):
        while state["step_count"] < state["max_agent_steps"]:
            if trace.paused or trace.exhausted:
                break
            try:
                apply_update(state, await dm_node(state, {}))
                message = last_ai_message(state["messages"])
                assert message is not None
                responses.append(
                    {
                        "step": state["step_count"] - 1,
                        "text": str(message.content),
                        "tool_calls": message.tool_calls,
                    }
                )
                if not message.tool_calls:
                    break
                apply_update(state, await tools_node(state))
                if route_after_tools(state) == "post_process_node":
                    break
            except Exception:
                failed.append("foreground-run-incomplete")
                break
    apply_update(state, post_process_node(state))
    first = next(
        (
            response["tool_calls"]
            for response in responses
            if any(call["name"] == "invoke_npc" for call in response["tool_calls"])
        ),
        [],
    )
    names = {
        call["args"].get("name", "").casefold() for call in first if call["name"] == "invoke_npc"
    }
    if not case.expected_initial_npcs <= names:
        failed.append("not-batched")
    has_second_beat = any(
        any(
            r.npc_name.casefold() == (case.expected_second_npc or "").casefold()
            for r in beat.results
        )
        for beat in state["npc_beats"][1:]
    )
    expect_second_beat = case.expected_second_npc is not None
    if expect_second_beat and not has_second_beat:
        failed.append("missing-dependent-beat")
    for response in responses:
        failed.extend(
            grade(
                PROBES_BY_NAME["npc_followup"], strip_markers(response["text"]), set(), sc.language
            )
        )
    actor_attempts = [
        attempt
        for attempt in trace.ledger.results()
        if attempt.key.startswith(f"{trace.key}|request-")
        and attempt.key not in previous_attempts
        and attempt.probe.endswith(":actor")
    ]
    return {
        "before": before,
        "after": state["world_state"],
        "character_after": state["char_data"],
        "quests_after": state["quests"].model_dump(mode="json"),
        "dm_steps": state["step_count"],
        "max_dm_calls": 3,
        "request_cap": trace.ceiling,
        "responses": responses,
        "beats": [asdict(beat) for beat in state["npc_beats"]],
        "registry": [
            {
                "handle": line.handle,
                "beat": line.beat,
                "step": line.step,
                "part": line.part.model_dump(mode="json"),
            }
            for line in state["npc_lines"]
        ],
        "parts": state["narration_segments"],
        "narration": state["narration"],
        "tool_results": [
            {"id": message.tool_call_id, "content": message.content}
            for message in state["messages"]
            if hasattr(message, "tool_call_id")
        ],
        "metrics": pipeline_metrics(
            state, responses, dispatches, actor_attempts, case, sc.language
        ),
    }, sorted(set(failed))
