"""DM graph nodes — context_node, dm_node, post_process_node."""

from __future__ import annotations

import json
import logging
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.ai.context import build_context
from app.ai.exceptions import PROVIDER_SDK_ERRORS, ContentPolicyError, provider_failure_message
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.router import get_user_generation
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.ai.tools.dm_tools import get_tool_schemas
from app.ai.tools.tool_groups import resolve_active_tools_from_state
from app.config import settings
from app.core.death import check_player_death
from app.core.dm.dm_helpers import get_or_create_segment, messages_to_raw, raw_history_to_lc
from app.core.dm.game_state import GameState
from app.core.engine import CONTENT_POLICY_NARRATION
from app.exceptions import AIProviderError
from app.memory.world_state import advance_game_clock, migrate_world_state

_llm_io = logging.getLogger("llm_io")
logger = structlog.get_logger()

MAX_STEPS: int = getattr(settings, "saga_max_agent_steps", 5)


async def context_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    from sqlalchemy import select

    from app.dependencies import get_db_context
    from app.memory.recall import embed_recall_query, snapshot_recall_query
    from app.models.campaign import Campaign

    campaign_id = state["campaign_id"]

    player_action = sanitize_player_input(state["player_action"])
    if detect_injection(player_action):
        player_action = "[The player looks around cautiously]"

    _, model_cfg = await get_user_generation(state["user_id"])

    async with get_db_context() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign: Campaign = result.scalar_one()
        try:
            recall_snapshot = await snapshot_recall_query(db, campaign.id)
        except Exception:
            logger.exception("recall_snapshot_failed", campaign_id=campaign_id)
            recall_snapshot = None

    query_embedding = (
        await embed_recall_query(recall_snapshot, player_action) if recall_snapshot else None
    )

    async with get_db_context() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one()

        context = await build_context(campaign, player_action, db, query_embedding=query_embedding)

    lc_messages = raw_history_to_lc(context.messages[:-1])
    lc_messages.append(HumanMessage(content=player_action))

    return {
        "messages": lc_messages,
        "world_state": migrate_world_state(campaign.world_state or {}),
        "char_data": campaign.character_data or {},
        "world_baseline": campaign.world_baseline or {},
        "difficulty": str(campaign.difficulty),
        "model_used": model_cfg.model,
        "importance_score": context.importance_score,
        "system_prompt": context.system_prompt,
        "model_config": {
            "provider": model_cfg.provider,
            "model": model_cfg.model,
            "max_tokens": model_cfg.max_tokens,
        },
    }


async def dm_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    provider, model_cfg = await get_user_generation(state["user_id"])
    system_prompt = state["system_prompt"]
    allowed_tools = resolve_active_tools_from_state(state["world_state"])
    tool_schemas = get_tool_schemas(allowed=allowed_tools)

    logger.info(
        "dm_node_step",
        step=state["step_count"],
        tools=sorted(allowed_tools),
        tool_count=len(tool_schemas),
    )

    messages_raw = messages_to_raw(state["messages"])

    _llm_io.info(
        json.dumps(
            {
                "direction": "input",
                "step": state["step_count"],
                "model": model_cfg.model,
                "system_preview": system_prompt[:300],
                "messages_count": len(messages_raw),
                "tools": sorted(allowed_tools),
            },
            ensure_ascii=False,
        )
    )

    try:
        response = await provider.generate_with_tools(
            system_prompt=system_prompt,
            messages=messages_raw,
            tools=tool_schemas,
            model=model_cfg.model,
            max_tokens=model_cfg.max_tokens,
        )
    except PROVIDER_SDK_ERRORS as exc:
        raise AIProviderError(model_cfg.provider, provider_failure_message(exc)) from exc
    except ContentPolicyError:
        response_text = CONTENT_POLICY_NARRATION
        ai_msg = AIMessage(content=response_text, tool_calls=[])
        return {
            "messages": [ai_msg],
            "narration": state["narration"] + response_text,
            "step_count": state["step_count"] + 1,
        }

    text = response.text or ""
    tool_calls_raw = response.tool_calls

    _llm_io.info(
        json.dumps(
            {
                "direction": "output",
                "step": state["step_count"],
                "text_preview": text[:200],
                "tool_calls": [{"name": tc.name, "args": tc.arguments} for tc in tool_calls_raw],
            },
            ensure_ascii=False,
        )
    )

    lc_tool_calls = [
        {"id": tc.id, "name": tc.name, "args": tc.arguments, "type": "tool_call"}
        for tc in tool_calls_raw
    ]
    ai_msg = AIMessage(content=text, tool_calls=lc_tool_calls)
    signatures = {tc.id: tc.signature for tc in tool_calls_raw if tc.signature is not None}
    if signatures:
        ai_msg.additional_kwargs[TOOL_CALL_SIGNATURES_KEY] = signatures
    if response.text_signature is not None:
        ai_msg.additional_kwargs[TEXT_SIGNATURE_KEY] = response.text_signature

    return {
        "messages": [ai_msg],
        "narration": state["narration"] + text,
        "step_count": state["step_count"] + 1,
    }


def post_process_node(state: GameState) -> dict[str, Any]:
    world_state = dict(state["world_state"])
    char_data = dict(state["char_data"])
    narration_segments = list(state["narration_segments"])

    # Sync any narration from the final dm_node that skipped tools_node
    full_narration = state["narration"]
    if full_narration:
        covered = sum(len(seg.get("text", "")) for seg in narration_segments)
        if covered < len(full_narration):
            last_step = max(state["step_count"] - 1, 0)
            seg = get_or_create_segment(narration_segments, last_step)
            if not seg["text"]:
                seg["text"] = full_narration[covered:]

    if state["time_passed_minutes"] > 0:
        world_state = advance_game_clock(world_state, state["time_passed_minutes"])

    # The difficulty rides the state from context_node. It used to be read off
    # char_data, a key nothing ever wrote, so every campaign silently resolved as
    # "never dies" — Ironman included (ADR 0003 S3).
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

    return {
        "world_state": world_state,
        "death_event": death_event,
        "narration_segments": narration_segments,
    }
