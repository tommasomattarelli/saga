"""REST endpoint for player actions — replaces the WebSocket game handler."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_embedding
from app.ai.router import get_gameplay_config
from app.core.dm.dm_graph import dm_graph
from app.core.dm.game_state import GameState
from app.dependencies import get_db
from app.memory.compressor import compress_turn_to_summary, ensure_compression
from app.memory.fact_extractor import extract_and_store_facts
from app.memory.global_summary import update_global_summary
from app.memory.world_state import migrate_world_state
from app.models.campaign import Campaign, CampaignStatus
from app.models.save import Save
from app.models.turn import Turn
from app.models.user import User
from app.schemas.campaign import TurnResponse, TurnSubmit
from app.security.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter()

_MAX_RECURSION = 30  # LangGraph recursion limit (covers up to 5 DM steps × 2 nodes + buffer)


@router.post("/{campaign_id}/action", response_model=TurnResponse)
async def submit_action(
    campaign_id: uuid.UUID,
    body: TurnSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TurnResponse:
    """Process a player action and return the complete turn result."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.status != CampaignStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is not active")

    campaign.turn_number += 1
    turn_number = campaign.turn_number

    # Build initial GameState
    initial_state: GameState = {
        "player_action": body.action,
        "campaign_id": str(campaign_id),
        "messages": [],
        "world_state": migrate_world_state(campaign.world_state or {}),
        "char_data": campaign.character_data or {},
        "narration": "",
        "narration_segments": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "time_passed_minutes": 0,
        "model_used": "",
        "importance_score": 5,
        "step_count": 0,
        "consecutive_empty_steps": 0,
        "death_event": None,
        "system_prompt": "",
        "model_config": {},
    }

    try:
        final_state = await dm_graph.ainvoke(
            initial_state,
            config={"recursion_limit": _MAX_RECURSION},
        )
    except Exception as exc:
        logger.exception("dm_graph_error", campaign_id=str(campaign_id), error=str(exc))
        campaign.turn_number -= 1
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DM processing failed",
        ) from exc

    # Persist results to campaign
    campaign.world_state = final_state["world_state"]
    campaign.character_data = final_state["char_data"]

    narration = final_state["narration"]
    narration_segments = final_state["narration_segments"] or None
    dice_results = final_state["dice_results"] or None
    scene_mood = final_state.get("scene_mood", "neutral")
    tool_events = final_state.get("tool_events", [])

    summary = await compress_turn_to_summary(narration, body.action)
    embedding = await generate_embedding(summary)

    # Build legacy dice_rolls dict for journal backward-compat
    dice_rolls_flat: dict = {}
    for dr in (dice_results or []):
        dice_rolls_flat.update(dr.get("rolls", {}))

    turn = Turn(
        campaign_id=campaign.id,
        turn_number=turn_number,
        player_action=body.action,
        narration=narration,
        narration_segments=narration_segments,
        dice_rolls=dice_rolls_flat or None,
        companion_actions=None,
        world_updates={"tool_events": tool_events},
        scene_mood=scene_mood,
        suggested_actions=None,
        model_used=final_state.get("model_used", ""),
        importance_score=final_state.get("importance_score", 5),
        summary=summary,
        embedding=embedding,
    )
    db.add(turn)

    await db.execute(
        delete(Save).where(Save.campaign_id == campaign.id, Save.is_auto == True)  # noqa: E712
    )
    db.add(
        Save(
            campaign_id=campaign.id,
            name="Auto-save",
            turn_number=turn_number,
            scene_summary=summary,
            is_auto=True,
            campaign_snapshot={
                "character_data": campaign.character_data,
                "world_state": campaign.world_state,
                "quests": campaign.quests,
                "turn_number": turn_number,
            },
        )
    )

    await db.commit()
    logger.info("turn_completed", turn=turn_number, model=final_state.get("model_used", ""))

    # Background tasks (fire-and-forget)
    asyncio.create_task(
        extract_and_store_facts(
            campaign_id=campaign.id,
            turn_number=turn_number,
            player_action=body.action,
            narration=narration,
            npc_dialogues=[
                f"{d['npc_name']}: {d['dialogue']}"
                for d in (final_state.get("npc_dialogues") or [])
            ] or None,
        )
    )
    asyncio.create_task(_background_compression(campaign.id, turn_number))

    gp_cfg = get_gameplay_config()
    if (
        gp_cfg.global_summary_enabled
        and turn_number > 0
        and turn_number % max(1, gp_cfg.global_summary_update_every) == 0
    ):
        asyncio.create_task(_background_global_summary(campaign.id, turn_number))

    combat_state = campaign.world_state.get("combat_state") if campaign.world_state else None

    return TurnResponse(
        turn_number=turn_number,
        player_action=body.action,
        narration=narration,
        narration_segments=narration_segments,
        dice_results=dice_results,
        dice_rolls=dice_rolls_flat or None,
        npc_dialogues=final_state.get("npc_dialogues") or None,
        world_state=campaign.world_state or {},
        character_data=campaign.character_data or {},
        scene_mood=scene_mood,
        combat_state=combat_state if (combat_state and combat_state.get("active")) else None,
        tool_events=tool_events,
        death_event=final_state.get("death_event"),
        model_used=final_state.get("model_used", ""),
        importance_score=final_state.get("importance_score", 5),
        time_passed_minutes=final_state.get("time_passed_minutes", 0),
        requires_player_action=True,
    )


async def _background_compression(campaign_id: uuid.UUID, current_turn: int) -> None:
    from app.dependencies import get_db_context

    try:
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), current_turn, db)
            await db.commit()
    except Exception:
        logger.exception("background_compression_failed", campaign_id=str(campaign_id))


async def _background_global_summary(campaign_id: uuid.UUID, current_turn: int) -> None:
    from app.dependencies import get_db_context

    try:
        async with get_db_context() as db:
            await update_global_summary(campaign_id, current_turn, db)
            await db.commit()
    except Exception:
        logger.exception("background_global_summary_failed", campaign_id=str(campaign_id))
