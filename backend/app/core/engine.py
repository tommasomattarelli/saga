"""Turn processing pipeline - the heart of the game engine."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import build_context
from app.ai.exceptions import ContentPolicyError
from app.ai.npc_director import NPCDialogue, format_npc_dialogues_for_turn, invoke_npcs_parallel
from app.ai.parser import parse_dm_response
from app.ai.router import AICallType, route_ai_call
from app.ai.semantic_resolver import resolve_player_action
from app.ai.stream_extractor import NarrationExtractor
from app.core.death import check_player_death
from app.core.dice import ability_check
from app.memory.updater import apply_typed_updates
from app.memory.world_state import advance_game_clock, apply_world_updates, migrate_world_state
from app.models.campaign import Campaign, CampaignStatus

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

    logger.info(
        "ai_raw_response",
        campaign_id=str(campaign.id),
        turn_number=campaign.turn_number,
        raw_length=len(raw_response),
        raw_preview=raw_response[:500],
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
            if campaign.character_data and roll_request.name in (
                campaign.character_data.get("abilities") or {}
            ):
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
    in_combat = (campaign.world_state or {}).get("combat_state", {}).get("active", False)
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


@dataclass
class StreamEvent:
    """An event yielded during streaming turn processing."""

    type: Literal[
        "narration_chunk",
        "dice_roll",
        "dice_narration_chunk",
        "scene_mood",
        "npc_dialogue",
        "combat_start",
        "combat_end",
        "death_event",
        "turn_result",
        "error",
    ]
    data: str | dict


async def process_game_turn_streaming(
    campaign: Campaign,
    player_action: str,
    db: AsyncSession,
) -> AsyncIterator[StreamEvent]:
    """Process a game turn with streaming narration.

    Yields StreamEvents as the LLM generates tokens. The full response is
    accumulated in parallel for JSON parsing after the stream completes.
    """
    # Semantic Resolver: resolve implicit references before context assembly
    resolver_output = await resolve_player_action(player_action, campaign, db)
    logger.debug(
        "semantic_resolver",
        target_npcs=resolver_output.target_npcs,
        target_locations=resolver_output.target_locations,
    )

    context = await build_context(campaign, player_action, db)
    model_config = await route_ai_call(AICallType.DM_NARRATION, context)

    from app.ai.providers.base import get_provider

    provider = get_provider(model_config.provider)

    # Stream the DM response, extracting narration tokens in real time
    raw_response = ""
    extractor = NarrationExtractor()

    try:
        async for chunk in provider.stream(
            system_prompt=context.system_prompt,
            messages=context.messages,
            model=model_config.model,
            temperature=model_config.temperature,
        ):
            raw_response += chunk
            narration_text = extractor.feed(chunk)
            if narration_text:
                yield StreamEvent(type="narration_chunk", data=narration_text)
    except ContentPolicyError:
        yield StreamEvent(type="error", data=CONTENT_POLICY_NARRATION)
        return

    logger.info(
        "ai_raw_response",
        campaign_id=str(campaign.id),
        turn_number=campaign.turn_number,
        raw_length=len(raw_response),
        raw_preview=raw_response[:500],
    )
    parsed = parse_dm_response(raw_response)

    # Handle character creation
    if parsed.character_generation and isinstance(parsed.character_generation, dict):
        campaign.character_data = parsed.character_generation
        await db.flush()
        logger.info("character_generated", name=parsed.character_generation.get("name"))

    # Send scene mood immediately
    yield StreamEvent(type="scene_mood", data=parsed.scene_mood or "neutral")

    # Execute dice rolls and stream the re-prompt narration
    dice_results = None
    dice_narration = ""
    if parsed.dice_required:
        dice_results = {}
        for roll_request in parsed.dice_required:
            effective_modifier = roll_request.modifier
            if campaign.character_data and roll_request.name in (
                campaign.character_data.get("abilities") or {}
            ):
                ability_score = campaign.character_data["abilities"][roll_request.name]
                effective_modifier = (ability_score - 10) // 2

            check_result = ability_check(
                modifier=effective_modifier,
                dc=roll_request.dc,
                advantage=roll_request.advantage,
                disadvantage=roll_request.disadvantage,
            )
            roll_data = check_result["roll"]
            roll_dict = {
                "expression": roll_data.expression,
                "rolls": roll_data.rolls,
                "modifier": roll_data.modifier,
                "total": roll_data.total,
                "dc": check_result["dc"],
                "success": check_result["success"],
                "outcome": check_result["outcome"],
                "is_critical": check_result["is_critical"],
            }
            dice_results[roll_request.name] = roll_dict

            yield StreamEvent(type="dice_roll", data={"name": roll_request.name, **roll_dict})

            # Stream the dice re-prompt narration
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

            dice_extractor = NarrationExtractor()
            dice_raw = ""
            try:
                async for chunk in provider.stream(
                    system_prompt=context.system_prompt,
                    messages=re_prompt_messages,
                    model=model_config.model,
                    temperature=model_config.temperature,
                ):
                    dice_raw += chunk
                    narr = dice_extractor.feed(chunk)
                    if narr:
                        yield StreamEvent(type="dice_narration_chunk", data=narr)
                re_parsed = parse_dm_response(dice_raw)
                dice_narration += "\n\n" + re_parsed.narration
            except ContentPolicyError:
                dice_narration += "\n\n" + "The outcome unfolds..."
                yield StreamEvent(type="dice_narration_chunk", data="\n\nThe outcome unfolds...")

    full_narration = parsed.narration
    if dice_narration:
        full_narration += dice_narration

    # NPC Actor-Director: invoke NPCs in parallel
    npc_dialogues: list[NPCDialogue] = []
    if parsed.invoke_npcs:
        npc_dialogues = await invoke_npcs_parallel(
            parsed.invoke_npcs,
            campaign,
            player_action,
            parsed.narration,
        )
        for npc_d in npc_dialogues:
            yield StreamEvent(
                type="npc_dialogue",
                data={
                    "npc_name": npc_d.npc_name,
                    "dialogue": npc_d.dialogue,
                    "action": npc_d.action,
                },
            )

        # Append NPC dialogues to narration for turn record
        npc_text = format_npc_dialogues_for_turn(npc_dialogues)
        if npc_text:
            full_narration += npc_text

        # Apply NPC disposition changes
        disposition_updates = [
            {"key": "npc_disposition", "target": d.npc_name, "change": d.disposition_change}
            for d in npc_dialogues
            if d.disposition_change != 0
        ]
        if disposition_updates:
            new_state, new_char = apply_typed_updates(
                campaign.world_state or {}, campaign.character_data or {}, disposition_updates
            )
            campaign.world_state = new_state
            campaign.character_data = new_char
            await db.flush()

    # Advance GameClock
    current_state = migrate_world_state(campaign.world_state)
    updated_state = advance_game_clock(current_state, parsed.time_passed_minutes)
    campaign.world_state = updated_state
    await db.flush()

    # Apply world updates (typed array first, legacy dict fallback)
    if parsed.world_updates:
        if isinstance(parsed.world_updates, list):
            # Typed updates array (primary format)
            keys = [u.get("key", "?") for u in parsed.world_updates]
            logger.info("world_updates_applying", format="list", count=len(keys), keys=keys)
            new_state, new_char = apply_typed_updates(
                campaign.world_state or {}, campaign.character_data or {}, parsed.world_updates
            )
            campaign.world_state = new_state
            campaign.character_data = new_char
            await db.flush()
        elif isinstance(parsed.world_updates, dict):
            # Legacy dict format: generic merge
            logger.info("world_updates_applying", format="dict_legacy")
            await apply_world_updates(campaign, parsed.world_updates, db)

    # Combat state events
    combat_state = (campaign.world_state or {}).get("combat_state", {})
    if combat_state.get("active"):
        yield StreamEvent(type="combat_start", data=combat_state)

    # Death check — runs after all world updates (including combat_damage)
    death_result = None
    char_data = campaign.character_data or {}
    if char_data.get("hp", {}).get("current", 1) <= 0:
        death_result = check_player_death(
            char_data, campaign.death_mode, campaign.world_state or {}
        )
        campaign.character_data = char_data  # cronista may have reset HP
        if death_result.destino_lives_remaining is not None:
            campaign.world_state["destino_lives"] = death_result.destino_lives_remaining
        if death_result.is_dead:
            campaign.status = CampaignStatus.COMPLETED
        await db.flush()
        yield StreamEvent(
            type="death_event",
            data={
                "is_dead": death_result.is_dead,
                "action": death_result.action,
                "death_mode": death_result.death_mode,
                "narrative_instruction": death_result.narrative_instruction,
                "destino_lives_remaining": death_result.destino_lives_remaining,
            },
        )

    if not combat_state.get("active") and combat_state.get("round", 0) == 0:
        # Combat just ended (was active before, now reset)
        pass  # combat_end is implicit in the updated combat_state

    in_combat = combat_state.get("active", False)
    requires_player_action = bool(in_combat or parsed.dice_required)

    yield StreamEvent(
        type="turn_result",
        data={
            "narration": full_narration,
            "dice_rolls": dice_results,
            "companion_actions": parsed.companion_actions,
            "world_updates": parsed.world_updates,
            "scene_mood": parsed.scene_mood,
            "suggested_actions": parsed.suggested_actions,
            "model_used": model_config.model,
            "importance_score": context.importance_score,
            "invoke_npcs": parsed.invoke_npcs,
            "time_passed_minutes": parsed.time_passed_minutes,
            "ambient_detail": parsed.ambient_detail,
            "requires_player_action": requires_player_action,
            "combat_state": combat_state if combat_state.get("active") else None,
            "death_event": {
                "is_dead": death_result.is_dead,
                "action": death_result.action,
                "death_mode": death_result.death_mode,
                "destino_lives_remaining": death_result.destino_lives_remaining,
            }
            if death_result
            else None,
            "npc_dialogues": [
                {"npc_name": d.npc_name, "dialogue": d.dialogue, "action": d.action}
                for d in npc_dialogues
            ],
            "character_data": campaign.character_data,
            "world_state": campaign.world_state,
        },
    )
