from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.production_policy import configured_memory_policy
from app.models.campaign import Campaign
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemoryState


class HistoryContractError(ValueError):
    pass


def require_campaign_history(campaign: Campaign) -> None:
    if (
        campaign.memory_policy_id is None
        or campaign.active_continuation_id is None
        or campaign.active_memory_state_id is None
    ):
        raise HistoryContractError(
            "Campaign history is not initialized for the current memory contract."
        )


async def initialize_campaign_history(db: AsyncSession, campaign: Campaign) -> None:
    if any(
        value is not None
        for value in (
            campaign.memory_policy_id,
            campaign.active_continuation_id,
            campaign.active_head_turn_id,
            campaign.active_memory_state_id,
        )
    ):
        raise HistoryContractError(
            "Campaign history is already initialized or partially configured."
        )

    await db.flush()
    policy = configured_memory_policy()
    policy_id = uuid.uuid4()
    continuation_id = uuid.uuid4()
    state_id = uuid.uuid4()
    db.add(
        MemoryPolicy(
            id=policy_id,
            campaign_id=campaign.id,
            schema_version=1,
            payload=policy,
            payload_hash=policy.policy_hash(),
        )
    )
    db.add(
        HistoryContinuation(
            id=continuation_id,
            campaign_id=campaign.id,
            parent_continuation_id=None,
            fork_head_turn_id=None,
        )
    )
    db.add(
        MemoryState(
            id=state_id,
            campaign_id=campaign.id,
            policy_id=policy_id,
            context_epoch=0,
            global_checkpoint_id=None,
            last_compacted_batch_id=None,
            revision=0,
        )
    )
    campaign.memory_policy_id = policy_id
    campaign.active_continuation_id = continuation_id
    campaign.active_head_turn_id = None
    campaign.active_memory_state_id = state_id
    campaign.context_epoch = 0
    campaign.fork_on_next_action = False
    await db.flush()
