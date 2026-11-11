from uuid import uuid4

from pydantic import JsonValue
from sqlalchemy import func, update

from app import dependencies
from app.core.dm.game_state import GameState
from app.memory.job_lifecycle import wake_memory_worker
from app.memory.job_scheduler import coordinate_memory
from app.memory.operation_storage import add_operation_recording
from app.models.quest import QuestRegistry
from app.models.turn import Turn
from app.models.turn_request import TurnRequest
from app.schemas.campaign import TurnResponse, TurnSubmit
from app.services.action_claims import ActionClaim, load_action_claim
from app.services.action_errors import context_changed
from app.services.save_service import create_campaign_save


async def publish_action(claim: ActionClaim, body: TurnSubmit, state: GameState) -> TurnResponse:
    quests = QuestRegistry.model_validate(state["quests"])
    dice_rolls: dict[str, JsonValue] = {}
    for result in state.get("dice_results") or []:
        dice_rolls.update(result.get("rolls", {}))
    turn_id = uuid4()
    response = TurnResponse(
        request_id=claim.request_id,
        turn_id=turn_id,
        head_turn_id=turn_id,
        context_epoch=claim.context_epoch,
        turn_number=claim.turn_number,
        player_action=body.action,
        narration=state["narration"],
        narration_segments=state.get("narration_segments") or None,
        dice_results=state.get("dice_results") or None,
        dice_rolls=dice_rolls or None,
        world_state=state["world_state"],
        character_data=state["char_data"],
        quests=quests,
        scene_mood=state.get("scene_mood", "neutral"),
        tool_events=state.get("tool_events", []),
        death_event=state.get("death_event"),
        model_used=state.get("model_used", ""),
        importance_score=state.get("importance_score", 5),
        time_passed_minutes=state.get("time_passed_minutes", 0),
        requires_player_action=True,
    )
    async with dependencies.async_session() as db:
        campaign, _ = await load_action_claim(db, claim)
        campaign.world_state = state["world_state"]
        campaign.character_data = state["char_data"]
        campaign.quests = quests.model_dump()
        turn = Turn(
            id=turn_id,
            campaign_id=claim.campaign_id,
            turn_number=claim.turn_number,
            continuation_id=claim.continuation_id,
            parent_turn_id=claim.starting_head_turn_id,
            history_depth=claim.history_depth,
            player_action=body.action,
            narration=state["narration"],
            narration_segments=state.get("narration_segments") or None,
            dice_rolls=dice_rolls or None,
            scene_mood=response.scene_mood,
            world_updates={"tool_events": response.tool_events},
            model_used=response.model_used,
            importance_score=response.importance_score,
        )
        db.add(turn)
        add_operation_recording(db, turn, state.get("operations"))
        await db.flush()
        campaign.active_head_turn_id = turn.id
        await db.flush()
        await create_campaign_save(db, campaign, name="Auto-save", is_auto=True)
        await coordinate_memory(db, campaign.id)
        live = await db.scalar(
            update(TurnRequest)
            .where(
                TurnRequest.request_id == claim.request_id,
                TurnRequest.execution_token == claim.execution_token,
                TurnRequest.state == "running",
                TurnRequest.execution_expires_at > func.clock_timestamp(),
            )
            .values(
                state="committed",
                result_turn_id=turn.id,
                response_payload=response.model_dump(mode="json"),
                execution_token=None,
                execution_expires_at=None,
            )
            .returning(TurnRequest.request_id)
            .execution_options(synchronize_session=False)
        )
        if live is None:
            raise context_changed()
        campaign.active_action_request_id = None
        await db.commit()
    wake_memory_worker()
    return response
