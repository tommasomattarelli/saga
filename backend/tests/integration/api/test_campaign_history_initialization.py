import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemoryState


@pytest.mark.asyncio
async def test_new_campaign_gets_immutable_policy_root_and_empty_memory_state(
    auth_client, db_session
):
    response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "the-awakening", "name": "History Contract", "difficulty": "medium"},
    )

    assert response.status_code == 201
    campaign_id = response.json()["id"]
    campaign = await db_session.scalar(select(Campaign).where(Campaign.id == campaign_id))
    policy = await db_session.scalar(
        select(MemoryPolicy).where(MemoryPolicy.campaign_id == campaign_id)
    )
    continuation = await db_session.scalar(
        select(HistoryContinuation).where(HistoryContinuation.campaign_id == campaign_id)
    )
    state = await db_session.scalar(
        select(MemoryState).where(MemoryState.campaign_id == campaign_id)
    )

    assert campaign.memory_policy_id == policy.id
    assert policy.payload_hash == policy.payload.policy_hash()
    assert policy.payload.raw_turns == 8
    assert continuation.id == campaign.active_continuation_id
    assert continuation.parent_continuation_id is None
    assert continuation.fork_head_turn_id is None
    assert state.id == campaign.active_memory_state_id
    assert state.policy_id == policy.id
    assert state.context_epoch == campaign.context_epoch == 0
    assert state.global_checkpoint_id is None
    assert state.last_compacted_batch_id is None
