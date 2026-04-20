"""Semantic Resolver — resolves implicit references in player actions via budget LLM."""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.parser import _strip_fences
from app.ai.providers.base import get_provider, logged_generate
from app.ai.router import AICallType, route_ai_call
from app.models.campaign import Campaign
from app.models.turn import Turn

logger = structlog.get_logger()

RESOLVER_PROMPT = """Given the player's action and session context, resolve any implicit references.

Session context:
- Current location: {location}
- Active companions: {companions}
- Recent NPCs (last 3 turns): {recent_npcs}
- Recent locations: {recent_locations}

Player action: "{action}"

Resolve pronouns ("her", "him", "them", "it") and vague references ("the city nearby", "that merchant", "the weapon") to specific names using the session context.

Output ONLY valid JSON:
{{"target_npcs": ["resolved NPC names"], "target_locations": ["resolved location names"], "time_estimate_minutes": 5}}

Rules:
- Only include names you can confidently resolve from context
- If no implicit references found, return empty lists
- time_estimate_minutes: rough estimate (dialogue 1-5, exploration 10-30, travel 30-480)"""


class ResolverOutput(BaseModel):
    target_npcs: list[str] = []
    target_locations: list[str] = []
    time_estimate_minutes: int = 5


async def resolve_player_action(
    action: str,
    campaign: Campaign,
    db: AsyncSession,
) -> ResolverOutput:
    """Mini-call to budget model to resolve implicit references in player action."""
    # Extract session context from campaign state and recent turns
    world_state = campaign.world_state or {}
    location = world_state.get("meta", {}).get("current_location", "unknown")

    companions = []
    comp_data = world_state.get("companions", {})
    if isinstance(comp_data, dict):
        companions = list(comp_data.keys())
    elif isinstance(comp_data, list):
        companions = [c.get("name", "") for c in comp_data if isinstance(c, dict)]

    # Get recent NPCs and locations from last 3 turns
    result = await db.execute(
        select(Turn.narration)
        .where(Turn.campaign_id == campaign.id)
        .order_by(Turn.turn_number.desc())
        .limit(3)
    )
    # Recent narrations available for future context enrichment
    _ = [n for (n,) in result.all() if n]

    # Extract NPC names from world_state
    npcs_data = world_state.get("npcs", {})
    recent_npcs = list(npcs_data.keys()) if isinstance(npcs_data, dict) else []

    # Extract locations
    locations_data = world_state.get("locations", {})
    recent_locations = list(locations_data.keys()) if isinstance(locations_data, dict) else []

    prompt_text = RESOLVER_PROMPT.format(
        location=location,
        companions=", ".join(companions) if companions else "none",
        recent_npcs=", ".join(recent_npcs[:10]) if recent_npcs else "none",
        recent_locations=", ".join(recent_locations[:10]) if recent_locations else "none",
        action=action,
    )

    try:
        from app.ai.context import GameContext

        dummy_context = GameContext(
            system_prompt="",
            messages=[],
            importance_score=0,
            active_quests=[],
            recent_events=[],
        )
        model_config = await route_ai_call(AICallType.NPC_BEHAVIOR, dummy_context)
        provider = get_provider(model_config.provider)

        raw = await logged_generate(
            provider,
            caller="semantic_resolver",
            system_prompt="You resolve implicit references in RPG player actions.",
            messages=[{"role": "user", "content": prompt_text}],
            model=model_config.model,
            temperature=0.1,
            max_tokens=200,
        )

        cleaned = _strip_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            from json_repair import repair_json

            data = json.loads(repair_json(cleaned))

        if isinstance(data, list):
            data = data[0] if data else {}
        return ResolverOutput(**data)

    except Exception:
        logger.warning("semantic_resolver_failed", action=action[:100], exc_info=True)
        return ResolverOutput()
