"""DM graph nodes — context_node, dm_node, post_process_node."""

from __future__ import annotations

import json
import logging
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.ai.context import build_context
from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import get_provider
from app.ai.router import AICallType, route_ai_call
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.ai.tools.dm_tools import get_tool_schemas
from app.ai.tools.tool_groups import resolve_active_tools_from_state
from app.config import settings
from app.core.death import check_player_death
from app.core.dm.dm_helpers import get_or_create_segment, messages_to_raw, raw_history_to_lc
from app.core.dm.game_state import GameState
from app.core.engine import CONTENT_POLICY_NARRATION
from app.memory.world_state import advance_game_clock, migrate_world_state

_llm_io = logging.getLogger("llm_io")
logger = structlog.get_logger()

MAX_STEPS: int = getattr(settings, "saga_max_agent_steps", 5)


async def context_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    from sqlalchemy import select

    from app.ai.embeddings import generate_embedding
    from app.dependencies import get_db_context
    from app.models.campaign import Campaign

    campaign_id = state["campaign_id"]

    player_action = sanitize_player_input(state["player_action"])
    if detect_injection(player_action):
        player_action = "[The player looks around cautiously]"

    # Rule 15: compute the recall embedding before opening the session.
    query_embedding = await generate_embedding(player_action)

    async with get_db_context() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign: Campaign = result.scalar_one()

        context = await build_context(campaign, player_action, db, query_embedding=query_embedding)
        model_cfg = await route_ai_call(AICallType.DM_NARRATION, context)

    lc_messages = raw_history_to_lc(context.messages[:-1])
    lc_messages.append(HumanMessage(content=player_action))

    return {
        "messages": lc_messages,
        "world_state": migrate_world_state(campaign.world_state or {}),
        "char_data": campaign.character_data or {},
        "world_baseline": campaign.world_baseline or {},
        "model_used": model_cfg.model,
        "importance_score": context.importance_score,
        "system_prompt": context.system_prompt,
        "model_config": {
            "provider": model_cfg.provider,
            "model": model_cfg.model,
            "temperature": model_cfg.temperature,
            "max_tokens": model_cfg.max_tokens,
        },
    }


async def dm_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    from app.ai.router import ModelConfig

    raw_cfg = state["model_config"]
    model_cfg = ModelConfig(
        provider=raw_cfg["provider"],
        model=raw_cfg["model"],
        temperature=raw_cfg["temperature"],
        max_tokens=raw_cfg["max_tokens"],
    )

    provider = get_provider(model_cfg.provider)
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
            temperature=model_cfg.temperature,
            max_tokens=model_cfg.max_tokens,
        )
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

    death_mode = char_data.get("death_mode", "cronista")
    death_result = check_player_death(char_data, death_mode, world_state)
    death_event: dict | None = None
    if death_result.action != "alive":
        death_event = {
            "is_dead": death_result.is_dead,
            "action": death_result.action,
            "death_mode": death_result.death_mode,
            "narrative_instruction": death_result.narrative_instruction,
            "destino_lives_remaining": death_result.destino_lives_remaining,
        }

    return {
        "world_state": world_state,
        "death_event": death_event,
        "narration_segments": narration_segments,
    }
