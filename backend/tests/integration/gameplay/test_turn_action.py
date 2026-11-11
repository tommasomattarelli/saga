"""Action endpoint failure, response and memory-cutover regressions."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.exceptions import AIProviderError
from app.models.campaign import Campaign, CampaignStatus
from app.models.source_embedding import SourceEmbedding
from app.models.turn import Turn
from app.models.turn_request import TurnRequest
from tests.action_support import action_body

pytestmark = pytest.mark.usefixtures("configured_generation")


def _fake_state(**overrides) -> dict:
    base = {
        "world_state": {"meta": {"current_location": "Town"}},
        "char_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        "quests": {"active": [], "completed": [], "failed": [], "abandoned": []},
        "narration": "The dust settles.",
        "narration_segments": None,
        "dice_results": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "death_event": None,
        "model_used": "test-model",
        "importance_score": 5,
        "time_passed_minutes": 0,
    }
    base.update(overrides)
    return base


async def _create_campaign(auth_client) -> str:
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Action Campaign",
            "difficulty": "medium",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_dm_graph_failure_returns_500_without_persisting_turn(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    body = await action_body(auth_client, campaign_id, "do something")

    with patch(
        "app.api.turns.dm_graph.ainvoke", new=AsyncMock(side_effect=RuntimeError("graph boom"))
    ):
        response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)

    assert response.status_code == 500
    assert response.json()["detail"] == "DM processing failed"
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
        )
        == 0
    )
    campaign = await db_session.get(Campaign, uuid.UUID(campaign_id), populate_existing=True)
    assert campaign is not None and campaign.turn_number == 1
    request = await db_session.get(TurnRequest, uuid.UUID(body["request_id"]))
    assert request is not None and request.state == "interrupted"


@pytest.mark.asyncio
async def test_action_does_not_write_per_turn_summary_or_turn_embedding(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    body = await action_body(auth_client, campaign_id, "look around")

    with patch("app.api.turns.dm_graph.ainvoke", new=AsyncMock(return_value=_fake_state())):
        response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)

    assert response.status_code == 200, response.text
    turn = await db_session.scalar(select(Turn).where(Turn.campaign_id == campaign_id))
    assert turn is not None
    assert turn.summary is None
    assert (
        await db_session.scalar(
            select(SourceEmbedding.id).where(SourceEmbedding.campaign_id == campaign_id)
        )
        is None
    )
    assert response.json()["request_id"] == body["request_id"]
    assert response.json()["turn_id"] == response.json()["head_turn_id"]


@pytest.mark.asyncio
async def test_provider_failure_returns_502_without_persisting_turn(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    body = await action_body(auth_client, campaign_id, "do something")
    with patch(
        "app.api.turns.dm_graph.ainvoke",
        new=AsyncMock(
            side_effect=AIProviderError("local", "Rate limit exceeded: free-models-per-day")
        ),
    ):
        response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)

    assert response.status_code == 502
    assert "free-models-per-day" in response.json()["detail"]
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_action_on_missing_campaign_returns_404(auth_client):
    campaign_id = str(uuid.uuid4())
    response = await auth_client.post(
        f"/api/campaigns/{campaign_id}/action",
        json={
            "action": "do something",
            "request_id": str(uuid.uuid4()),
            "expected_head_turn_id": None,
            "expected_context_epoch": 0,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "campaign_not_found"


@pytest.mark.asyncio
async def test_action_on_inactive_campaign_returns_400(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    campaign.status = CampaignStatus.COMPLETED
    await db_session.commit()
    body = await action_body(auth_client, campaign_id, "do something")

    response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "campaign_inactive"


@pytest.mark.asyncio
async def test_dice_results_are_flattened_into_dice_rolls(auth_client):
    campaign_id = await _create_campaign(auth_client)
    body = await action_body(auth_client, campaign_id, "roll some dice")
    state = _fake_state(dice_results=[{"rolls": {"d20": 15}}, {"rolls": {"d6": 4}}])

    with patch("app.api.turns.dm_graph.ainvoke", new=AsyncMock(return_value=state)):
        response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)

    assert response.status_code == 200, response.text
    assert response.json()["dice_rolls"] == {"d20": 15, "d6": 4}
