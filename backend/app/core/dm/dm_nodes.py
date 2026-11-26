"""DM graph nodes — context_node, dm_node, post_process_node."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, cast
from uuid import uuid4

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.ai.context import build_context
from app.ai.generation_errors import Adapter
from app.ai.generation_execution_ledger import (
    GenerationExecutionError,
    GenerationOutcomeStatus,
    InMemoryGenerationLedger,
)
from app.ai.prompts.dm import DMPromptContext, DMPromptState, render_dm_prompt
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.providers.usage import usage_scope
from app.ai.router import get_generation_recovery_policy, get_user_generation
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.ai.session_affinity import campaign_session_affinity
from app.core.death import check_player_death
from app.core.dm.dialogue_composition import clean_narration, compose_segments, transcript
from app.core.dm.dialogue_reminder import dialogue_reminder
from app.core.dm.dm_generation import (
    build_dm_generation_request,
    canonical_tool_arguments,
    execute_dm_generation,
)
from app.core.dm.dm_helpers import get_or_create_segment, messages_to_raw, raw_history_to_lc
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import closing_step, dm_call_limit, step_tools
from app.core.dm.npc_context import NarrativeObservation
from app.core.dm.npc_results import flush_interaction_history
from app.core.dm.operation_recorder import OperationRecorder
from app.core.npc_resolver import npcs_at_current_location
from app.exceptions import AIProviderError
from app.memory.operation_delta import OperationState
from app.memory.operation_results import DeathResult
from app.models.quest import QuestRegistry

_llm_io = logging.getLogger("llm_io")
logger = structlog.get_logger()


async def context_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    from sqlalchemy import select

    from app.dependencies import get_db_context
    from app.memory.context_snapshot import capture_turn_context
    from app.memory.query_construction import build_scene_anchor
    from app.memory.recall import embed_recall_query
    from app.memory.recall_config import get_recall_config
    from app.models.campaign import Campaign

    campaign_id = state["campaign_id"]

    player_action = sanitize_player_input(state["player_action"])
    if detect_injection(player_action):
        player_action = "[The player looks around cautiously]"

    _, model_cfg = await get_user_generation(state["user_id"])

    turn_context = state.get("turn_context")
    if turn_context is None:
        async with get_db_context() as db:
            result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
            campaign: Campaign = result.scalar_one()
            turn_context = await capture_turn_context(db, campaign)
    elif str(turn_context.campaign_id) != campaign_id:
        raise ValueError("The turn context does not match the requested campaign.")
    recall_snapshot = turn_context.recall_snapshot

    recall_config = get_recall_config()
    anchor = build_scene_anchor(
        turn_context.scene.world_state,
        turn_context.scene.world_baseline,
        turn_context.history,
        recall_snapshot.known_names if recall_snapshot else (),
        include_scene=recall_config.query.include_scene,
        recent_turns=recall_config.query.recent_narration_turns,
        max_chars=recall_config.query.anchor_max_chars,
    )
    query_embedding = (
        await embed_recall_query(recall_snapshot, player_action, anchor)
        if recall_snapshot
        else None
    )

    async with get_db_context() as db:
        context = await build_context(
            turn_context, player_action, db, query_embedding=query_embedding
        )

    lc_messages = raw_history_to_lc(cast(list[dict], context.messages[:-1]))
    lc_messages.append(HumanMessage(content=player_action))

    return {
        "player_action": player_action,
        "messages": lc_messages,
        "world_state": copy.deepcopy(turn_context.scene.world_state),
        "char_data": copy.deepcopy(turn_context.scene.character_data),
        "quests": copy.deepcopy(turn_context.scene.quests),
        "world_baseline": copy.deepcopy(turn_context.scene.world_baseline),
        "difficulty": turn_context.difficulty,
        "model_used": model_cfg.model,
        "importance_score": context.importance_score,
        "system_prompt": context.system_prompt,
        "prompt_context": context.prompt_context,
        "turn_context": turn_context,
        "model_config": {
            "provider": model_cfg.provider,
            "model": model_cfg.model,
            "max_tokens": model_cfg.max_tokens,
        },
    }


async def dm_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    if state["step_count"] >= dm_call_limit(state):
        raise ValueError("DM call budget exhausted.")
    provider, model_cfg = await get_user_generation(state["user_id"])
    closing = closing_step(state)
    allowed_tools = step_tools(state["world_state"], closing=closing)
    system_prompt = step_system_prompt(state, allowed_tools, closing)

    logger.info(
        "dm_node_step",
        step=state["step_count"],
        tools=sorted(allowed_tools),
        tool_count=len(allowed_tools),
    )

    messages_raw = messages_to_raw(state["messages"])
    turn_context = state.get("turn_context")
    previous_head_turn_id = (
        str(turn_context.head_turn_id)
        if turn_context is not None and turn_context.head_turn_id is not None
        else None
    )
    request = build_dm_generation_request(
        system_prompt,
        cast(list[dict[str, object]], messages_raw),
        config=model_cfg,
        allowed_tools=allowed_tools,
        campaign_id=state["campaign_id"],
        player_action=state["player_action"],
        step=state["step_count"],
        previous_head_turn_id=previous_head_turn_id,
        session_affinity=campaign_session_affinity(),
    )

    _llm_io.info(
        json.dumps(
            {
                "event": "generation_input",
                "step": state["step_count"],
                "model": model_cfg.model,
                "messages_count": len(messages_raw),
                "tool_count": len(request.tool_declarations),
            },
            ensure_ascii=False,
        )
    )

    try:
        with usage_scope(role="dm", step=state["step_count"]):
            execution = await execute_dm_generation(
                request,
                provider,
                InMemoryGenerationLedger(),
                get_generation_recovery_policy(),
                Adapter(model_cfg.provider),
            )
    except GenerationExecutionError as exc:
        raise AIProviderError(model_cfg.provider, str(exc)) from exc

    receipt = next(
        (
            outcome.receipt
            for outcome in reversed(execution.sends)
            if outcome.status is GenerationOutcomeStatus.VALID and outcome.receipt is not None
        ),
        None,
    )
    if receipt is None:
        raise RuntimeError("Successful DM generation did not retain its raw receipt.")

    text = execution.value.text or ""
    tool_calls_raw = receipt.tool_calls

    _llm_io.info(
        json.dumps(
            {
                "event": "generation_output",
                "step": state["step_count"],
                "model": model_cfg.model,
                "tool_call_count": len(tool_calls_raw),
            },
            ensure_ascii=False,
        )
    )

    lc_tool_calls = []
    wire_tool_calls = []
    signatures: dict[str, bytes] = {}
    for call in tool_calls_raw:
        call_id = call.call_id if call.call_id is not None else f"saga-call-{uuid4().hex}"
        lc_tool_calls.append(
            {
                "id": call_id,
                "name": call.name or "",
                "args": canonical_tool_arguments(call, request),
                "type": "tool_call",
            }
        )
        wire_tool_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": (
                        call.arguments.raw_text_value
                        if call.arguments.kind == "raw_text"
                        else json.dumps(call.arguments.structured_value, ensure_ascii=False)
                    ),
                },
            }
        )
        if call.signature is not None:
            signatures[call_id] = call.signature

    ai_msg = AIMessage(content=text, tool_calls=lc_tool_calls)
    if receipt.text is not None:
        ai_msg.additional_kwargs["generation_text"] = receipt.text
    if wire_tool_calls:
        ai_msg.additional_kwargs["tool_calls"] = wire_tool_calls
    if signatures:
        ai_msg.additional_kwargs[TOOL_CALL_SIGNATURES_KEY] = signatures
    if receipt.text_signature is not None:
        ai_msg.additional_kwargs[TEXT_SIGNATURE_KEY] = receipt.text_signature

    public_text, removed = clean_narration(
        text, state["step_count"], state["narration_segments"], state.get("npc_lines", [])
    )

    return {
        "messages": [ai_msg],
        "narration": state["narration"] + public_text,
        "dialogue_echo_removals": state.get("dialogue_echo_removals", 0) + removed,
        "step_count": state["step_count"] + 1,
        "allowed_tools": sorted(allowed_tools),
        "closing_step": closing,
        "system_prompt": system_prompt,
        **_record_narration(state, public_text),
    }


def step_system_prompt(state: GameState, allowed_tools: set[str], closing: bool) -> str:
    context = state.get("prompt_context") or DMPromptContext()
    scene = DMPromptState(
        state["world_state"],
        state["char_data"],
        state.get("world_baseline") or {},
        state.get("quests") or QuestRegistry(),
    )
    prompt = render_dm_prompt(scene, context, allowed_tools, closing=closing)
    reminder = dialogue_reminder(
        state.get("npc_lines", []),
        state.get("npc_beats", []),
        state["narration_segments"],
        context.language,
        closing or "invoke_npc" not in allowed_tools,
    )
    return f"{prompt}\n\n{reminder}"


def _record_narration(state: GameState, text: str) -> dict:
    segments = copy.deepcopy(state["narration_segments"])
    step = state["step_count"]
    get_or_create_segment(segments, step)["text"] = text
    observation = NarrativeObservation(
        step,
        text,
        frozenset(npcs_at_current_location(state["world_state"])),
        state["world_state"].get("meta", {}).get("current_location", ""),
    )
    return {
        "narration_segments": segments,
        "narrative_observations": [*state.get("narrative_observations", []), observation],
    }


def post_process_node(state: GameState) -> dict[str, Any]:
    world_state = copy.deepcopy(state["world_state"])
    char_data = copy.deepcopy(state["char_data"])
    operations = OperationRecorder(state.get("operations", []))
    step = max(state["step_count"] - 1, 0)
    segments = compose_segments(state["narration_segments"], state.get("npc_lines", []))
    flush_interaction_history(world_state, state.get("npc_beats", []), operations, step=step)

    # The difficulty rides the state from context_node. It used to be read off
    # char_data, a key nothing ever wrote, so every campaign silently resolved as
    # "never dies" — Ironman included (ADR 0003 S3).
    before = OperationState.capture(world_state, char_data, {})
    death_result = check_player_death(char_data, state["difficulty"], world_state)
    death_event: dict | None = None
    if death_result.action != "alive":
        death_event = {
            "is_dead": death_result.is_dead,
            "action": death_result.action,
            "difficulty": death_result.difficulty,
            "narrative_instruction": death_result.narrative_instruction,
            "fate_interventions_remaining": death_result.fate_interventions_remaining,
        }
        if death_result.fate_interventions_remaining is not None:
            world_state["fate_interventions_left"] = death_result.fate_interventions_remaining

    operations.append(
        origin="finalization",
        name="check_player_death",
        arguments={"difficulty": state["difficulty"]},
        outcome="succeeded",
        step=step,
        before=before,
        after=OperationState.capture(world_state, char_data, {}),
        result=DeathResult.model_validate(
            {
                "description": death_result.narrative_instruction or "Death policy checked.",
                "action": death_result.action,
                "is_dead": death_result.is_dead,
                "fate_interventions_remaining": death_result.fate_interventions_remaining,
            }
        ),
    )

    return {
        "world_state": world_state,
        "char_data": char_data,
        "operations": operations.records,
        "death_event": death_event,
        "narration": transcript(segments),
        "narration_segments": [segment.model_dump(mode="json") for segment in segments],
    }
