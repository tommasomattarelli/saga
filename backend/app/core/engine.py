"""Turn processing pipeline - the heart of the game engine."""

import json
import structlog
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import route_ai_call, AICallType
from app.ai.context import build_context
from app.ai.parser import parse_dm_response
from app.core.dice import roll_dice, ability_check
from app.models.campaign import Campaign
from app.models.turn import Turn

logger = structlog.get_logger()


@dataclass
class ProcessedTurn:
    """The fully processed result of a game turn."""

    narration: str
    dice_rolls: dict | None
    companion_actions: dict | None
    world_updates: dict | None
    scene_mood: str | None
    suggested_actions: list[str] | None
    model_used: str
    importance_score: int


async def process_game_turn(
    campaign: Campaign,
    player_action: str,
    db: AsyncSession,
) -> ProcessedTurn:
    """Process a complete game turn.

    Pipeline:
    1. Build context from campaign state + memory
    2. Route to appropriate AI model
    3. Get DM response
    4. Parse structured output
    5. Execute any dice rolls
    6. Apply world updates
    7. Return processed turn
    """
    # 1. Build context
    context = await build_context(campaign, player_action, db)

    # 2. Route to AI model based on scene importance
    model_config = await route_ai_call(AICallType.DM_NARRATION, context)

    # 3. Get DM response from AI
    from app.ai.providers.base import get_provider

    provider = get_provider(model_config.provider)
    raw_response = await provider.generate(
        system_prompt=context.system_prompt,
        messages=context.messages,
        model=model_config.model,
        temperature=model_config.temperature,
    )

    # 4. Parse structured output
    parsed = parse_dm_response(raw_response)

    # 5. Execute dice rolls if required
    dice_results = None
    if parsed.dice_required:
        dice_results = {}
        for roll_request in parsed.dice_required:
            result = ability_check(
                modifier=roll_request.get("modifier", 0),
                dc=roll_request.get("dc", 10),
            )
            dice_results[roll_request.get("name", "check")] = {
                "expression": result["roll"].expression,
                "rolls": result["roll"].rolls,
                "total": result["roll"].total,
                "dc": result["dc"],
                "success": result["success"],
            }

    # 6. Apply world updates to campaign state (validated + migrated)
    if parsed.world_updates:
        from app.memory.world_state import apply_world_updates
        await apply_world_updates(campaign, parsed.world_updates, db)

    return ProcessedTurn(
        narration=parsed.narration,
        dice_rolls=dice_results,
        companion_actions=parsed.companion_actions,
        world_updates=parsed.world_updates,
        scene_mood=parsed.scene_mood,
        suggested_actions=parsed.suggested_actions,
        model_used=model_config.model,
        importance_score=context.importance_score,
    )
