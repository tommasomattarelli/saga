from uuid import UUID

import pytest

from app.api.campaigns import get_campaign
from app.api.journal import get_journal
from app.api.saves import create_save, load_save
from app.models.campaign import Campaign
from app.schemas.save import SaveCreate
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result

pytestmark = pytest.mark.usefixtures("configured_generation")


async def test_load_refreshes_preloaded_campaign_before_incrementing_epoch(
    auth_client,
    db_session,
    test_user,
) -> None:
    campaign_id, _ = await campaign_and_action(auth_client)
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Beginning"})
    campaign_uuid, save_uuid = UUID(campaign_id), UUID(saved.json()["id"])
    cached = await db_session.get(Campaign, campaign_uuid)
    assert cached is not None and cached.context_epoch == 0
    first = await auth_client.post(f"/api/saves/{campaign_id}/load/{save_uuid}")
    assert first.status_code == 200 and first.json()["context_epoch"] == 1
    loaded = await load_save(campaign_uuid, save_uuid, test_user["user"], db_session)
    assert loaded["context_epoch"] == 2


async def test_manual_save_refreshes_preloaded_head(
    auth_client,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    campaign_uuid = UUID(campaign_id)
    cached = await db_session.get(Campaign, campaign_uuid)
    assert cached is not None and cached.active_head_turn_id is None

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    played = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert played.status_code == 200
    head = UUID(played.json()["head_turn_id"])
    saved = await create_save(
        campaign_uuid, SaveCreate(name="Current"), test_user["user"], db_session
    )
    assert saved.head_turn_id == head and saved.turn_number == 1


async def test_campaign_read_refreshes_preloaded_head(
    auth_client,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    campaign_uuid = UUID(campaign_id)
    cached = await db_session.get(Campaign, campaign_uuid)
    assert cached is not None and cached.active_head_turn_id is None

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    played = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert played.status_code == 200
    current = await get_campaign(campaign_uuid, test_user["user"], db_session)
    assert current.active_head_turn_id == UUID(played.json()["head_turn_id"])


async def test_journal_does_not_use_preloaded_future_after_restore(
    auth_client,
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Beginning"})

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    played = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert played.status_code == 200
    campaign_uuid = UUID(campaign_id)
    cached = await db_session.get(Campaign, campaign_uuid)
    assert cached is not None and cached.active_head_turn_id is not None
    loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{saved.json()['id']}")
    assert loaded.status_code == 200
    journal = await get_journal(campaign_uuid, user=test_user["user"], db=db_session)
    assert journal == []
