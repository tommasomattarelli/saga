"""REST endpoint for player actions — replaces the WebSocket game handler."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.generation_context import generation_context
from app.ai.router import get_gameplay_config, validate_user_generation
from app.api.rate_limit import limiter, turns_limit
from app.core.dm.dm_graph import dm_graph
from app.core.dm.game_state import GameState
from app.dependencies import get_db, get_db_context
from app.exceptions import AIProviderError, ValidationError
from app.memory.compressor import compress_turn_to_summary, ensure_compression
from app.memory.embedding_queue import enqueue_source_embedding
from app.memory.fact_extractor import extract_and_store_facts
from app.memory.global_summary import update_global_summary
from app.memory.world_state import migrate_world_state
from app.models.campaign import Campaign, CampaignStatus
from app.models.save import Save
from app.models.source_embedding import EmbeddingSourceType
from app.models.turn import Turn
from app.models.user import User
from app.schemas.campaign import TurnResponse, TurnSubmit
from app.security.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter()

_MAX_RECURSION = 30  # LangGraph recursion limit (covers up to 5 DM steps × 2 nodes + buffer)


@router.post("/{campaign_id}/action", response_model=TurnResponse)
@limiter.limit(turns_limit)
async def submit_action(
    request: Request,
    campaign_id: uuid.UUID,
    body: TurnSubmit,
    user: User = Depends(get_current_user),
    auth_db: AsyncSession = Depends(get_db),
) -> TurnResponse:
    await auth_db.close()
    with generation_context(user.id):
        return await _submit_action(request, campaign_id, body, user)


async def _submit_action(
    request: Request, campaign_id: uuid.UUID, body: TurnSubmit, user: User
) -> TurnResponse:
    """Process a player action and return the complete turn result.

    Rule 15: DB sessions never span the LLM/graph call. We open a short session to
    validate + atomically claim a turn number, close it, run the graph and embedding
    with no session held, then open a second session to persist the result.
    """
    request.state.rate_limit_user_id = str(user.id)

    # Session 1: validate + atomically claim the next turn number, then close.
    async with get_db_context() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == user.id)
        )
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        if campaign.status != CampaignStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is not active"
            )
        try:
            validate_user_generation(user)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.message) from exc

        claim = await db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(turn_number=Campaign.turn_number + 1)
            .returning(Campaign.turn_number)
        )
        turn_number = claim.scalar_one()
        prior_world_state = migrate_world_state(campaign.world_state or {})
        prior_char_data = campaign.character_data or {}
        world_baseline = campaign.world_baseline or {}
        difficulty = str(campaign.difficulty)
        await db.commit()

    # Build initial GameState (no session held).
    initial_state: GameState = {
        "player_action": body.action,
        "campaign_id": str(campaign_id),
        "user_id": str(user.id),
        "messages": [],
        "world_state": prior_world_state,
        "char_data": prior_char_data,
        "world_baseline": world_baseline,
        "difficulty": difficulty,
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
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AIProviderError as exc:
        # Not our failure: the player can act on "rate limited", not on "DM processing failed".
        logger.warning("dm_provider_error", campaign_id=str(campaign_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        ) from exc
    except Exception as exc:
        logger.exception("dm_graph_error", campaign_id=str(campaign_id), error=str(exc))
        # The claimed turn_number is simply skipped — a gap is harmless.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DM processing failed",
        ) from exc

    new_world_state = final_state["world_state"]
    new_char_data = final_state["char_data"]
    narration = final_state["narration"]
    narration_segments = final_state["narration_segments"] or None
    dice_results = final_state["dice_results"] or None
    scene_mood = final_state.get("scene_mood", "neutral")
    tool_events = final_state.get("tool_events", [])

    summary = await compress_turn_to_summary(narration, body.action)

    # Build legacy dice_rolls dict for journal backward-compat
    dice_rolls_flat: dict = {}
    for dr in dice_results or []:
        dice_rolls_flat.update(dr.get("rolls", {}))

    # Session 2: persist the turn result. Re-fetch to mutate an attached instance.
    async with get_db_context() as db:
        result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
        campaign = result.scalar_one_or_none()
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        await db.execute(
            text("SELECT id FROM campaigns WHERE id = :cid FOR UPDATE"), {"cid": campaign_id}
        )
        campaign.world_state = new_world_state
        campaign.character_data = new_char_data

        turn = Turn(
            campaign_id=campaign_id,
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
        )
        db.add(turn)
        await db.flush()
        queued_indexes = await enqueue_source_embedding(
            db,
            campaign_id=campaign_id,
            source_type=EmbeddingSourceType.TURN,
            source_id=turn.id,
            source_text=summary,
        )

        await db.execute(
            delete(Save).where(Save.campaign_id == campaign_id, Save.is_auto == True)  # noqa: E712
        )
        db.add(
            Save(
                campaign_id=campaign_id,
                name="Auto-save",
                turn_number=turn_number,
                scene_summary=summary,
                is_auto=True,
                campaign_snapshot={
                    "character_data": new_char_data,
                    "world_state": new_world_state,
                    "quests": campaign.quests,
                    "turn_number": turn_number,
                },
            )
        )

        await db.commit()

    if queued_indexes:
        from app.memory.embedding_worker import wake_embedding_worker

        wake_embedding_worker()

    logger.info("turn_completed", turn=turn_number, model=final_state.get("model_used", ""))

    # Background tasks (fire-and-forget) — each opens its own session.
    asyncio.create_task(
        extract_and_store_facts(
            campaign_id=campaign_id,
            turn_number=turn_number,
            player_action=body.action,
            narration=narration,
            npc_dialogues=[
                f"{d['npc_name']}: {d['dialogue']}"
                for d in (final_state.get("npc_dialogues") or [])
            ]
            or None,
        )
    )
    asyncio.create_task(_background_compression(campaign_id, turn_number))

    gp_cfg = get_gameplay_config()
    if (
        gp_cfg.global_summary_enabled
        and turn_number > 0
        and turn_number % max(1, gp_cfg.global_summary_update_every) == 0
    ):
        asyncio.create_task(_background_global_summary(campaign_id, turn_number))

    return TurnResponse(
        turn_number=turn_number,
        player_action=body.action,
        narration=narration,
        narration_segments=narration_segments,
        dice_results=dice_results,
        dice_rolls=dice_rolls_flat or None,
        npc_dialogues=final_state.get("npc_dialogues") or None,
        world_state=new_world_state or {},
        character_data=new_char_data or {},
        scene_mood=scene_mood,
        tool_events=tool_events,
        death_event=final_state.get("death_event"),
        model_used=final_state.get("model_used", ""),
        importance_score=final_state.get("importance_score", 5),
        time_passed_minutes=final_state.get("time_passed_minutes", 0),
        requires_player_action=True,
    )


async def _background_compression(campaign_id: uuid.UUID, current_turn: int) -> None:
    try:
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), current_turn, db)
            await db.commit()
        from app.memory.embedding_worker import wake_embedding_worker

        wake_embedding_worker()
    except Exception:
        logger.exception("background_compression_failed", campaign_id=str(campaign_id))


async def _background_global_summary(campaign_id: uuid.UUID, current_turn: int) -> None:
    try:
        async with get_db_context() as db:
            await update_global_summary(campaign_id, current_turn, db)
            await db.commit()
    except Exception:
        logger.exception("background_global_summary_failed", campaign_id=str(campaign_id))
