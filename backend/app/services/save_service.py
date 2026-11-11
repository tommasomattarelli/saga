from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.job_scheduler import coordinate_memory
from app.models.campaign import Campaign
from app.models.memory_document import MemoryState
from app.models.save import Save
from app.models.turn_request import TurnRequest


class SaveHistoryError(ValueError):
    pass


def _history_fields(campaign: Campaign) -> tuple[UUID | None, UUID | None, UUID | None]:
    return (
        campaign.active_continuation_id,
        campaign.active_head_turn_id,
        campaign.memory_policy_id,
    )


async def _active_memory_state(db: AsyncSession, campaign: Campaign) -> MemoryState | None:
    if campaign.memory_policy_id is None:
        if any(_history_fields(campaign)) or campaign.active_memory_state_id is not None:
            raise SaveHistoryError("Campaign history state is inconsistent.")
        return None
    if campaign.active_continuation_id is None or campaign.active_memory_state_id is None:
        raise SaveHistoryError("Campaign history state is incomplete.")
    state = await db.scalar(
        select(MemoryState).where(
            MemoryState.id == campaign.active_memory_state_id,
            MemoryState.campaign_id == campaign.id,
            MemoryState.policy_id == campaign.memory_policy_id,
            MemoryState.context_epoch == campaign.context_epoch,
        )
    )
    if state is None:
        raise SaveHistoryError("Campaign memory state is inconsistent.")
    return state


async def create_campaign_save(
    db: AsyncSession, campaign: Campaign, *, name: str, is_auto: bool = False
) -> Save:
    state = await _active_memory_state(db, campaign)
    save = Save(
        campaign_id=campaign.id,
        name=name,
        turn_number=campaign.turn_number,
        scene_summary=f"Turn {campaign.turn_number}",
        is_auto=is_auto,
        campaign_snapshot={
            "character_data": deepcopy(campaign.character_data or {}),
            "world_state": deepcopy(campaign.world_state or {}),
            "quests": deepcopy(campaign.quests or {}),
            "turn_number": campaign.turn_number,
        },
        continuation_id=campaign.active_continuation_id,
        head_turn_id=campaign.active_head_turn_id,
        memory_policy_id=campaign.memory_policy_id,
        global_checkpoint_id=state.global_checkpoint_id if state else None,
        last_compacted_batch_id=state.last_compacted_batch_id if state else None,
    )
    db.add(save)
    return save


async def restore_campaign_save(db: AsyncSession, campaign: Campaign, save: Save) -> int:
    if campaign.memory_policy_id is None or save.memory_policy_id is None:
        raise SaveHistoryError("This campaign save has no restorable history contract.")
    if save.memory_policy_id != campaign.memory_policy_id or save.continuation_id is None:
        raise SaveHistoryError("This campaign save has an incompatible history contract.")

    snapshot = save.campaign_snapshot
    campaign.character_data = deepcopy(snapshot.get("character_data") or {})
    campaign.world_state = deepcopy(snapshot.get("world_state") or {})
    campaign.quests = deepcopy(snapshot.get("quests") or {})
    campaign.turn_number = snapshot.get("turn_number", save.turn_number)
    campaign.active_continuation_id = save.continuation_id
    campaign.active_head_turn_id = save.head_turn_id
    campaign.context_epoch += 1
    campaign.fork_on_next_action = True

    if campaign.active_action_request_id is not None:
        await db.execute(
            update(TurnRequest)
            .where(
                TurnRequest.request_id == campaign.active_action_request_id,
                TurnRequest.campaign_id == campaign.id,
                TurnRequest.state == "running",
            )
            .values(
                state="invalidated",
                execution_token=None,
                execution_expires_at=None,
                error="Action invalidated because campaign history was restored.",
            )
        )
        campaign.active_action_request_id = None

    restored_state = MemoryState(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=save.memory_policy_id,
        context_epoch=campaign.context_epoch,
        global_checkpoint_id=save.global_checkpoint_id,
        last_compacted_batch_id=save.last_compacted_batch_id,
        revision=0,
    )
    db.add(restored_state)
    campaign.active_memory_state_id = restored_state.id
    await db.flush()
    await coordinate_memory(db, campaign.id)
    return campaign.turn_number
