"""Game WebSocket handler for real-time turn streaming."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, select

from app.ai.embeddings import generate_embedding
from app.ai.sanitizer import detect_injection, sanitize_player_input
from app.core.agent import DmAgent
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
                dice_rolls_accumulated: dict = {}
                segments_by_step: dict[int, dict] = {}
                dice_reveal_event = asyncio.Event()
                agent = DmAgent(campaign, dice_reveal_event)

                def _segment_for(step: int, segments_by_step: dict[int, dict] = segments_by_step) -> dict:
                    seg = segments_by_step.get(step)
                    if seg is None:
                        seg = {"step": step, "text": "", "dice": None, "npc_dialogues": []}
                        segments_by_step[step] = seg
                    return seg

                try:
                    async for event in agent.run(action, db):
                        step_idx = event.step_index if event.step_index is not None else 0
                        if event.type == "narration_chunk":
                            if isinstance(event.data, str):
                                _segment_for(step_idx)["text"] += event.data
                            await websocket.send_json(
                                {
                                    "type": "dm:narration:chunk",
                                    "chunk": event.data,
                                    "step_index": step_idx,
                                }
                            )
                        elif event.type == "dice_roll":
                            if isinstance(event.data, dict):
                                dice_rolls_accumulated.update(event.data)
                                seg = _segment_for(step_idx)
                                seg["dice"] = {**(seg["dice"] or {}), **event.data}
                            await websocket.send_json(
                                {
                                    "type": "dice:roll",
                                    "step_index": step_idx,
                                    **(event.data if isinstance(event.data, dict) else {}),
                                }
                            )
                        elif event.type == "await_player":
                            # Clear BEFORE the blocking loop so agent.wait() blocks
                            # correctly when the generator is advanced after this handler.
                            dice_reveal_event.clear()
                            await websocket.send_json({"type": "await:dice_reveal"})
                            # Drain incoming messages until client sends dice_revealed
                            while True:
                                client_msg = await websocket.receive_json()
                                if client_msg.get("type") == "dice_revealed":
                                    dice_reveal_event.set()
                                    break
                                # Ignore other messages during pause
                        elif event.type == "scene_mood":
                            await websocket.send_json({"type": "scene_mood", "mood": event.data})
                        elif event.type == "npc_dialogue":
                            npc_data = event.data if isinstance(event.data, dict) else {}
                            _segment_for(step_idx)["npc_dialogues"].append(npc_data)
                            await websocket.send_json(
                                {"type": "npc:dialogue", "step_index": step_idx, **npc_data}
                            )
                            npc_name = npc_data.get("npc_name", "NPC")
                            dialogue = npc_data.get("dialogue", "")
                            npc_dialogues_for_facts.append(f"{npc_name}: {dialogue}")
                        elif event.type == "tool_executed":
                            tool_data = event.data if isinstance(event.data, dict) else {}
                            await websocket.send_json({"type": "tool:executed", **tool_data})
                            # Forward combat tool events with legacy types for frontend compat
                            tool_name = tool_data.get("tool", "")
                            if tool_name == "start_combat":
                                extra = tool_data.get("extra", {})
                                await websocket.send_json({"type": "combat:start", **extra})
                            elif tool_name == "end_combat":
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
                except WebSocketDisconnect:
                    raise
                except Exception as exc:
                    log.exception("turn_processing_error", error=str(exc))
                    try:
                        await websocket.send_json(
                            {"type": "error", "message": "Turn processing failed"}
                        )
                    except Exception:
                        pass
                    campaign.turn_number -= 1
                    continue

                if turn_result is None:
                    campaign.turn_number -= 1
                    continue

                # Persist turn to DB
                narration = turn_result["narration"]
                # Update campaign world/character state from agent output
                campaign.world_state = turn_result["world_state"]
                campaign.character_data = turn_result["character_data"]

                summary = await compress_turn_to_summary(narration, action)
                embedding = await generate_embedding(summary)
                narration_segments = (
                    [segments_by_step[k] for k in sorted(segments_by_step.keys())]
                    if segments_by_step
                    else None
                )
                turn = Turn(
                    campaign_id=campaign.id,
                    turn_number=turn_number,
                    player_action=action,
                    narration=narration,
                    narration_segments=narration_segments,
                    dice_rolls=dice_rolls_accumulated or None,
                    companion_actions=None,
                    world_updates={"tool_events": turn_result.get("tool_events", [])},
                    scene_mood=turn_result.get("scene_mood"),
                    suggested_actions=None,
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

                try:
                    await websocket.send_json(
                        {
                            "type": "turn_complete",
                            "turn_number": turn_number,
                            "player_action": action,
                            "narration_segments": narration_segments,
                            "dice_rolls": dice_rolls_accumulated or None,
                            **turn_result,
                        }
                    )
                except Exception:
                    log.warning("ws_send_turn_complete_failed", turn=turn_number)

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
