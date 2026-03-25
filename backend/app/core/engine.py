"""Turn processing pipeline - the heart of the game engine."""

from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_context
from app.ai.exceptions import ContentPolicyError
from app.ai.parser import parse_dm_response
from app.ai.router import AICallType, route_ai_call
from app.core.dice import ability_check
from app.memory.world_state import advance_game_clock, apply_world_updates, migrate_world_state
from app.models.campaign import Campaign

logger = structlog.get_logger()

CONTENT_POLICY_NARRATION = (
    "The DM refuses to narrate this scene as described. Try rephrasing your action."
)

DICE_RE_PROMPT_TEMPLATE = (
    'The player attempted "{check}". They rolled {roll} + {modifier} = {total} vs DC {dc}. '
    "Outcome: {outcome}. Narrate the result in 2-3 sentences."
)


@dataclass
class ProcessedTurn:
    """The fully processed result of a game turn."""

    narration: str
    dice_rolls: dict | None
    companion_actions: dict[str, str] | None
    world_updates: dict | None
    scene_mood: str | None
    suggested_actions: list[str] | None
    model_used: str
    importance_score: int
    invoke_npcs: list[str] = field(default_factory=list)
    time_passed_minutes: int = 5
    ambient_detail: str | None = None
    requires_player_action: bool = True


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
    4. Parse structured output (with JSON healing)
    5. If dice_required: roll immediately + re-prompt for result narration
    6. Advance GameClock
    7. Apply world updates
    8. Return processed turn
    """
    context = await build_context(campaign, player_action, db)
    model_config = await route_ai_call(AICallType.DM_NARRATION, context)

    from app.ai.providers.base import get_provider

    provider = get_provider(model_config.provider)

    try:
        raw_response = await provider.generate(
            system_prompt=context.system_prompt,
            messages=context.messages,
            model=model_config.model,
            temperature=model_config.temperature,
        )
    except ContentPolicyError:
        return ProcessedTurn(
            narration=CONTENT_POLICY_NARRATION,
            dice_rolls=None,
            companion_actions=None,
            world_updates=None,
            scene_mood="neutral",
            suggested_actions=None,
            model_used=model_config.model,
            importance_score=context.importance_score,
            requires_player_action=True,
        )

    parsed = parse_dm_response(raw_response)

    # Handle character creation
    if parsed.character_generation and isinstance(parsed.character_generation, dict):
        campaign.character_data = parsed.character_generation
        await db.flush()
        logger.info("character_generated", name=parsed.character_generation.get("name"))

    # Execute dice rolls and re-prompt
    dice_results = None
    dice_narration = ""
    if parsed.dice_required:
        dice_results = {}
        for roll_request in parsed.dice_required:
            # Read modifier from character_data if available
            effective_modifier = roll_request.modifier
            if campaign.character_data and roll_request.name in (campaign.character_data.get("abilities") or {}):
                ability_score = campaign.character_data["abilities"][roll_request.name]
                effective_modifier = (ability_score - 10) // 2

            check_result = ability_check(
                modifier=effective_modifier,
                dc=roll_request.dc,
                advantage=roll_request.advantage,
                disadvantage=roll_request.disadvantage,
            )
            roll_data = check_result["roll"]
            dice_results[roll_request.name] = {
                "expression": roll_data.expression,
                "rolls": roll_data.rolls,
                "modifier": roll_data.modifier,
                "total": roll_data.total,
                "dc": check_result["dc"],
                "success": check_result["success"],
                "outcome": check_result["outcome"],
                "is_critical": check_result["is_critical"],
            }

            # Re-prompt: ask DM to narrate the dice result
            re_prompt_msg = DICE_RE_PROMPT_TEMPLATE.format(
                check=roll_request.name,
                roll=roll_data.rolls[0] if roll_data.rolls else roll_data.total,
                modifier=roll_data.modifier,
                total=roll_data.total,
                dc=check_result["dc"],
                outcome=check_result["outcome"],
            )
            re_prompt_messages = context.messages + [
                {"role": "assistant", "content": raw_response},
                {"role": "user", "content": re_prompt_msg},
            ]

            try:
                dice_narration_raw = await provider.generate(
                    system_prompt=context.system_prompt,
                    messages=re_prompt_messages,
                    model=model_config.model,
                    temperature=model_config.temperature,
                )
                # The re-prompt response might be JSON or plain text
                re_parsed = parse_dm_response(dice_narration_raw)
                dice_narration += "\n\n" + re_parsed.narration
            except ContentPolicyError:
                dice_narration += "\n\n" + "The outcome unfolds..."

    full_narration = parsed.narration
    if dice_narration:
        full_narration += dice_narration

    # Advance GameClock
    current_state = migrate_world_state(campaign.world_state)
    updated_state = advance_game_clock(current_state, parsed.time_passed_minutes)
    campaign.world_state = updated_state
    await db.flush()

    # Apply world updates from DM
    if parsed.world_updates:
        await apply_world_updates(campaign, parsed.world_updates, db)

    # Determine if the player needs to act
    in_combat = campaign.world_state.get("in_combat", False)
    requires_player_action = bool(in_combat or parsed.dice_required)

    return ProcessedTurn(
        narration=full_narration,
        dice_rolls=dice_results,
        companion_actions=parsed.companion_actions,
        world_updates=parsed.world_updates,
        scene_mood=parsed.scene_mood,
        suggested_actions=parsed.suggested_actions,
        model_used=model_config.model,
        importance_score=context.importance_score,
        invoke_npcs=parsed.invoke_npcs,
        time_passed_minutes=parsed.time_passed_minutes,
        ambient_detail=parsed.ambient_detail,
        requires_player_action=requires_player_action,
    )
