"""Game WebSocket handler for real-time turn streaming."""

import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.security.auth import decode_token

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

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "")

            if not action:
                await websocket.send_json({"error": "No action provided"})
                continue

            # Process turn via the game engine
            # For now, send a placeholder response
            await websocket.send_json({
                "type": "turn_start",
                "turn_number": 0,
            })

            # TODO: stream narration chunks as they arrive from the AI
            await websocket.send_json({
                "type": "narration",
                "text": f"[AI DM would respond to: {action}]",
            })

            await websocket.send_json({
                "type": "turn_complete",
            })

    except WebSocketDisconnect:
        pass
