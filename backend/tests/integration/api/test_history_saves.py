from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.memory_document import MemoryState
from app.models.save import Save
from app.models.turn_request import TurnRequest
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)
from tests.integration.memory.test_job_publication import _claimed_job


@pytest.mark.asyncio
async def test_save_load_restores_history_and_invalidates_inflight_action(
    auth_client: AsyncClient, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    campaign = fixture.campaign
    first = await fixture.turn(number=1)
    original_head = await fixture.turn(first, number=2)
    other_continuation = await fixture.fork(first)
    other_future = await fixture.turn(first, continuation=other_continuation, number=2)

    state = MemoryState(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=fixture.policy.id,
        context_epoch=campaign.context_epoch,
        global_checkpoint_id=None,
        last_compacted_batch_id=None,
        revision=0,
    )
    fixture.session.add(state)
    campaign.active_memory_state_id = state.id
    campaign.active_head_turn_id = original_head.id
    campaign.active_continuation_id = fixture.root.id
    campaign.character_data = {"nested": {"hp": 20}}
    campaign.world_state = {"location": "Inn"}
    campaign.quests = {"active": [], "completed": [], "failed": [], "abandoned": []}
    campaign.turn_number = 2
    await fixture.session.commit()

    save_response = await auth_client.post(
        f"/api/saves/{campaign.id}", json={"name": "Before fork"}
    )
    assert save_response.status_code == 201
    save_id = save_response.json()["id"]

    request_id = uuid4()
    other_state = MemoryState(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=fixture.policy.id,
        context_epoch=1,
        global_checkpoint_id=None,
        last_compacted_batch_id=None,
        revision=0,
    )
    fixture.session.add(other_state)
    campaign.context_epoch = 1
    campaign.active_memory_state_id = other_state.id
    campaign.active_head_turn_id = other_future.id
    campaign.active_continuation_id = other_continuation.id
    campaign.fork_on_next_action = False
    await fixture.session.commit()

    later_save = await auth_client.post(
        f"/api/saves/{campaign.id}", json={"name": "Future branch"}
    )
    assert later_save.status_code == 201
    later_save_id = later_save.json()["id"]

    running = TurnRequest(
        request_id=request_id,
        campaign_id=campaign.id,
        payload_hash="a" * 64,
        starting_head_turn_id=original_head.id,
        context_epoch=campaign.context_epoch,
        state="running",
        execution_token=uuid4(),
        execution_expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        claimed_turn_number=3,
    )
    fixture.session.add(running)
    campaign.active_action_request_id = request_id
    campaign.turn_number = 2
    await fixture.session.commit()

    load_response = await auth_client.post(f"/api/saves/{campaign.id}/load/{save_id}")
    assert load_response.status_code == 200
    assert load_response.json()["active_head_turn_id"] == str(original_head.id)
    assert load_response.json()["context_epoch"] == 2

    await fixture.session.refresh(campaign)
    await fixture.session.refresh(running)
    assert campaign.active_head_turn_id == original_head.id
    assert campaign.active_continuation_id == fixture.root.id
    assert campaign.fork_on_next_action is True
    assert campaign.active_action_request_id is None
    assert campaign.active_memory_state_id != state.id
    assert running.state == "invalidated"
    assert running.execution_token is None
    assert running.execution_expires_at is None

    journal = await auth_client.get(f"/api/journal/{campaign.id}")
    assert journal.status_code == 200
    rows = journal.json()
    assert {row["turn_id"] for row in rows} == {str(first.id), str(original_head.id)}
    assert str(other_future.id) not in {row["turn_id"] for row in rows}

    saved = await fixture.session.scalar(select(Save).where(Save.id == save_id))
    assert saved is not None
    assert saved.head_turn_id == original_head.id
    assert saved.continuation_id == fixture.root.id
    assert saved.campaign_snapshot["character_data"] == {"nested": {"hp": 20}}
    later = await fixture.session.scalar(select(Save).where(Save.id == later_save_id))
    assert later is not None
    assert later.head_turn_id == other_future.id
    saves = await auth_client.get(f"/api/saves/{campaign.id}")
    assert {item["id"] for item in saves.json()} == {save_id, later_save_id}


@pytest.mark.asyncio
async def test_legacy_save_is_readable_but_cannot_be_loaded_as_new_history(
    auth_client: AsyncClient, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    campaign = fixture.campaign
    campaign.memory_policy_id = None
    campaign.active_continuation_id = None
    campaign.active_head_turn_id = None
    campaign.active_memory_state_id = None
    campaign.character_data = {"hp": 9}
    await fixture.session.commit()

    created = await auth_client.post(
        f"/api/saves/{campaign.id}", json={"name": "Legacy checkpoint"}
    )
    assert created.status_code == 201
    save_id = created.json()["id"]
    listed = await auth_client.get(f"/api/saves/{campaign.id}")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == save_id

    loaded = await auth_client.post(f"/api/saves/{campaign.id}/load/{save_id}")
    assert loaded.status_code == 409
    assert loaded.json()["detail"]["code"] == "campaign_history_required"


@pytest.mark.asyncio
async def test_empty_history_head_is_a_valid_save_and_restore(
    auth_client: AsyncClient, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    campaign = fixture.campaign
    state = MemoryState(
        id=uuid4(),
        campaign_id=campaign.id,
        policy_id=fixture.policy.id,
        context_epoch=campaign.context_epoch,
        global_checkpoint_id=None,
        last_compacted_batch_id=None,
        revision=0,
    )
    fixture.session.add(state)
    campaign.active_memory_state_id = state.id
    campaign.active_head_turn_id = None
    await fixture.session.commit()

    saved = await auth_client.post(f"/api/saves/{campaign.id}", json={"name": "Beginning"})
    assert saved.status_code == 201
    save_id = saved.json()["id"]

    restored = await auth_client.post(f"/api/saves/{campaign.id}/load/{save_id}")
    assert restored.status_code == 200
    assert restored.json()["active_head_turn_id"] is None
    assert restored.json()["context_epoch"] == 1

    journal = await auth_client.get(f"/api/journal/{campaign.id}")
    assert journal.status_code == 200
    assert journal.json() == []


@pytest.mark.asyncio
async def test_restore_preserves_pending_memory_job_attempt_budget(
    auth_client: AsyncClient, history_fixture: HistoryFixture
) -> None:
    fixture = history_fixture
    job, _, _, _, old_state = await _claimed_job(fixture)
    attempts_before = job.attempt_count

    saved = await auth_client.post(f"/api/saves/{fixture.campaign.id}", json={"name": "Pending"})
    assert saved.status_code == 201
    loaded = await auth_client.post(f"/api/saves/{fixture.campaign.id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200

    await fixture.session.refresh(job)
    await fixture.session.refresh(old_state)
    restored_campaign = await fixture.session.get(Campaign, fixture.campaign.id)
    assert restored_campaign is not None
    await fixture.session.refresh(restored_campaign)
    restored_state = await fixture.session.get(
        MemoryState, restored_campaign.active_memory_state_id
    )
    assert restored_state is not None
    assert restored_state.id != old_state.id
    assert restored_state.last_compacted_batch_id is None
    assert old_state.last_compacted_batch_id is None
    assert job.attempt_count == attempts_before
    assert job.state == "running"
