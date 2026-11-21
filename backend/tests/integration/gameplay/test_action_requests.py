import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.campaign import Campaign, Difficulty
from app.models.turn import Turn
from app.models.turn_request import TurnRequest

pytestmark = pytest.mark.usefixtures("configured_generation")


def graph_result(state: dict) -> dict:
    return {
        **state,
        "narration": "A lantern is lit.",
        "narration_segments": [],
        "dice_results": [{"rolls": {"d20": 17}}],
        "time_passed_minutes": 3,
        "death_event": None,
        "model_used": "controlled-model",
    }


async def campaign_and_action(client) -> tuple[str, dict]:
    response = await client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Idempotency",
            "difficulty": "medium",
        },
    )
    assert response.status_code == 201
    campaign = response.json()
    return campaign["id"], {
        "action": "Light the lantern",
        "request_id": str(uuid4()),
        "expected_head_turn_id": campaign.get("active_head_turn_id"),
        "expected_context_epoch": campaign.get("context_epoch", 0),
    }


async def test_committed_retry_replays_exact_response_without_generation(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    calls = []

    async def generate(state, **kwargs):
        calls.append(state)
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    first = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    second = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1
    assert first.json()["request_id"] == body["request_id"]
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 1


async def test_payload_conflict_and_running_duplicate_never_generate_twice(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(state, **kwargs):
        started.set()
        await release.wait()
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    task = asyncio.create_task(auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body))
    try:
        await asyncio.wait_for(started.wait(), 5)
        duplicate = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "action_in_progress"
        conflict = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={**body, "action": "Leave"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "action_payload_conflict"
        other = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={**body, "request_id": str(uuid4())},
        )
        assert other.status_code == 409
        assert other.json()["detail"]["code"] == "action_in_progress"
    finally:
        release.set()
        result = await task
    assert result.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(TurnRequest)) == 1


async def test_load_fences_inflight_action_and_historical_replay(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    saved = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Before"})
    assert saved.status_code == 201
    started, release = asyncio.Event(), asyncio.Event()

    async def generate(state, **kwargs):
        started.set()
        await release.wait()
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    task = asyncio.create_task(auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body))
    try:
        await asyncio.wait_for(started.wait(), 5)
        loaded = await auth_client.post(f"/api/saves/{campaign_id}/load/{saved.json()['id']}")
        assert loaded.status_code == 200
    finally:
        release.set()
        response = await task
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "action_context_changed"
    campaign = await db_session.get(Campaign, UUID(campaign_id), populate_existing=True)
    assert campaign is not None and campaign.active_head_turn_id is None
    assert campaign.context_epoch == 1 and campaign.turn_number == 0
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 0


async def test_new_action_recovers_expired_slot_without_reexecuting_old_request(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    old_id = uuid4()
    request = TurnRequest(
        request_id=old_id,
        campaign_id=UUID(campaign_id),
        payload_hash="0" * 64,
        starting_head_turn_id=None,
        context_epoch=0,
        state="running",
        execution_token=uuid4(),
        claimed_turn_number=1,
        execution_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(request)
    campaign = await db_session.get(Campaign, UUID(campaign_id))
    assert campaign is not None
    campaign.active_action_request_id = old_id
    campaign.turn_number = 1
    await db_session.commit()

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert response.status_code == 200 and response.json()["turn_number"] == 2
    await db_session.refresh(request)
    assert request.state == "interrupted" and request.execution_token is None


async def test_legacy_campaign_cannot_accept_new_action(auth_client, db_session, test_user):
    campaign = Campaign(
        user_id=test_user["user"].id,
        name="Legacy",
        world_slug="test",
        difficulty=Difficulty.MEDIUM,
    )
    db_session.add(campaign)
    await db_session.commit()
    response = await auth_client.post(
        f"/api/campaigns/{campaign.id}/action",
        json={
            "action": "Look",
            "request_id": str(uuid4()),
            "expected_head_turn_id": None,
            "expected_context_epoch": 0,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "campaign_history_required"
    await db_session.refresh(campaign)
    assert campaign.turn_number == 0
