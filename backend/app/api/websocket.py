"""Game WebSocket handler for real-time turn streaming."""

from __future__ import annotations

import uuid
import structlog

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_context
from app.models.campaign import Campaign, CampaignStatus
from app.security.auth import decode_token
from app.core.engine import process_game_turn
from app.exceptions import UnauthorizedError, NotFoundError

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/{campaign_id}")
async def game_ws(
    websocket: WebSocket,
    campaign_id: uuid.UUID,
    token: str,
) -> None:
    """WebSocket endpoint for real-time game interaction."""
    # Authenticate
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    log = logger.bind(campaign_id=str(campaign_id), user_id=str(user_id))
    log.info("ws_connected")

    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Campaign).where(
                    Campaign.id == campaign_id,
                    Campaign.user_id == user_id,
                )
            )
            campaign = result.scalar_one_or_none()

            if campaign is None:
                await websocket.send_json({"type": "error", "message": "Campaign not found"})
                await websocket.close(code=4004, reason="Campaign not found")
                return

            if campaign.status != CampaignStatus.ACTIVE:
                await websocket.send_json({"type": "error", "message": "Campaign is not active"})
                await websocket.close(code=4003, reason="Campaign not active")
                return

            # Main turn loop
            while True:
                data = await websocket.receive_json()
                action = data.get("action", "").strip()

                if not action:
                    await websocket.send_json({"type": "error", "message": "No action provided"})
                    continue

                campaign.turn_number += 1
                turn_number = campaign.turn_number

                await websocket.send_json({"type": "turn_start", "turn_number": turn_number})

                try:
                    processed = await process_game_turn(campaign, action, db)
                except Exception as exc:
                    log.exception("turn_processing_error", error=str(exc))
                    await websocket.send_json({"type": "error", "message": "Turn processing failed"})
                    campaign.turn_number -= 1
                    continue

                # Stream narration (single chunk for now; replace with real streaming later)
                await websocket.send_json({"type": "narration", "text": processed.narration})

                if processed.dice_rolls:
                    await websocket.send_json({"type": "dice_rolls", "rolls": processed.dice_rolls})

                if processed.companion_actions:
                    await websocket.send_json({"type": "companions", "actions": processed.companion_actions})

                await websocket.send_json({"type": "scene_mood", "mood": processed.scene_mood or "neutral"})

                if processed.suggested_actions:
                    await websocket.send_json({"type": "suggestions", "actions": processed.suggested_actions})

                await websocket.send_json({"type": "turn_complete", "turn_number": turn_number})

                await db.commit()

                log.info("turn_completed", turn=turn_number, model=processed.model_used)

    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception as exc:
        log.exception("ws_unhandled_error", error=str(exc))
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
