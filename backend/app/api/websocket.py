"""Game WebSocket handler for real-time turn streaming."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, select

from app.ai.embeddings import generate_embedding
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.core.engine import process_game_turn_streaming
from app.dependencies import get_db_context
from app.memory.compressor import compress_turn_to_summary, ensure_compression
from app.memory.fact_extractor import extract_and_store_facts
from app.models.campaign import Campaign, CampaignStatus
from app.models.save import Save
from app.models.turn import Turn
from app.security.auth import decode_token

logger = structlog.get_logger()
router = APIRouter()


@router.websocket("/{campaign_id}")
async def game_ws(
    websocket: WebSocket,
    campaign_id: uuid.UUID,
    token: str,
) -> None:
    """WebSocket endpoint for real-time game interaction."""
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

            while True:
                data = await websocket.receive_json()
                action = data.get("action", "").strip()

                if not action:
                    await websocket.send_json({"type": "error", "message": "No action provided"})
                    continue

                action = sanitize_player_input(action)
                if detect_injection(action):
                    log.warning("prompt_injection_detected")
                    action = "[The player looks around cautiously]"

                campaign.turn_number += 1
                turn_number = campaign.turn_number

                await websocket.send_json({"type": "turn_start", "turn_number": turn_number})

                turn_result = None
                npc_dialogues_for_facts: list[str] = []
                try:
                    async for event in process_game_turn_streaming(campaign, action, db):
                        if event.type == "narration_chunk":
                            await websocket.send_json(
                                {"type": "dm:narration:chunk", "chunk": event.data}
                            )
                        elif event.type == "dice_roll":
                            await websocket.send_json(
                                {
                                    "type": "dice:roll",
                                    **(event.data if isinstance(event.data, dict) else {}),
                                }
                            )
                        elif event.type == "dice_narration_chunk":
                            await websocket.send_json(
                                {"type": "dice:narration:chunk", "chunk": event.data}
                            )
                        elif event.type == "scene_mood":
                            await websocket.send_json({"type": "scene_mood", "mood": event.data})
                        elif event.type == "npc_dialogue":
                            npc_data = event.data if isinstance(event.data, dict) else {}
                            await websocket.send_json({"type": "npc:dialogue", **npc_data})
                            npc_name = npc_data.get("npc_name", "NPC")
                            dialogue = npc_data.get("dialogue", "")
                            npc_dialogues_for_facts.append(f"{npc_name}: {dialogue}")
                        elif event.type == "combat_start":
                            await websocket.send_json(
                                {
                                    "type": "combat:start",
                                    **(event.data if isinstance(event.data, dict) else {}),
                                }
                            )
                        elif event.type == "combat_end":
                            await websocket.send_json({"type": "combat:end"})
                        elif event.type == "death_event":
                            await websocket.send_json(
                                {
                                    "type": "death:event",
                                    **(event.data if isinstance(event.data, dict) else {}),
                                }
                            )
                        elif event.type == "turn_result":
                            turn_result = event.data
                        elif event.type == "error":
                            await websocket.send_json({"type": "error", "message": event.data})
                except Exception as exc:
                    log.exception("turn_processing_error", error=str(exc))
                    await websocket.send_json(
                        {"type": "error", "message": "Turn processing failed"}
                    )
                    campaign.turn_number -= 1
                    continue

                if turn_result is None:
                    campaign.turn_number -= 1
                    continue

                # Persist turn to DB
                narration = turn_result["narration"]
                summary = await compress_turn_to_summary(narration, action)
                embedding = await generate_embedding(summary)
                turn = Turn(
                    campaign_id=campaign.id,
                    turn_number=turn_number,
                    player_action=action,
                    narration=narration,
                    dice_rolls=turn_result["dice_rolls"],
                    companion_actions=turn_result["companion_actions"],
                    world_updates=turn_result["world_updates"],
                    scene_mood=turn_result["scene_mood"],
                    suggested_actions=turn_result["suggested_actions"],
                    model_used=turn_result["model_used"],
                    importance_score=turn_result["importance_score"],
                    summary=summary,
                    embedding=embedding,
                )
                db.add(turn)

                await db.execute(
                    delete(Save).where(
                        Save.campaign_id == campaign.id,
                        Save.is_auto == True,  # noqa: E712
                    )
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

                await websocket.send_json(
                    {
                        "type": "turn_complete",
                        "turn_number": turn_number,
                        **turn_result,
                    }
                )

                await db.commit()

                log.info("turn_completed", turn=turn_number, model=turn_result["model_used"])

                # Background tasks (fire-and-forget, after commit)
                asyncio.create_task(
                    extract_and_store_facts(
                        campaign_id=campaign.id,
                        turn_number=turn_number,
                        player_action=action,
                        narration=narration,
                        npc_dialogues=npc_dialogues_for_facts or None,
                    )
                )
                asyncio.create_task(_background_compression(campaign.id, turn_number))

    except WebSocketDisconnect:
        log.info("ws_disconnected")
    except Exception as exc:
        log.exception("ws_unhandled_error", error=str(exc))
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


async def _background_compression(campaign_id: uuid.UUID, current_turn: int) -> None:
    """Compress old turns in the background after the main transaction commits."""
    try:
        async with get_db_context() as db:
            await ensure_compression(str(campaign_id), current_turn, db)
            await db.commit()
    except Exception:
        logger.exception("background_compression_failed", campaign_id=str(campaign_id))
