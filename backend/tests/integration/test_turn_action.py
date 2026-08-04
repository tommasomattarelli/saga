"""Coverage for the player-action endpoint's error path, dice flattening,
and the fire-and-forget background helpers (turns.py)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.api.turns import _background_compression, _background_global_summary
from app.exceptions import AIProviderError
from app.models.campaign import Campaign, CampaignStatus
from app.models.turn import Turn


def _fake_state(**overrides) -> dict:
    base = {
        "world_state": {"meta": {"current_location": "Town"}},
        "char_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        "narration": "The dust settles.",
        "narration_segments": None,
        "dice_results": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "npc_dialogues": [],
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
    """A graph crash yields a clean 500 and leaves no half-written turn — the
    claimed turn_number is simply skipped (gap is harmless)."""
    campaign_id = await _create_campaign(auth_client)

    with patch(
        "app.api.turns.dm_graph.ainvoke",
        new=AsyncMock(side_effect=RuntimeError("graph boom")),
    ):
        resp = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={"action": "do something"},
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "DM processing failed"

    turn_count = await db_session.scalar(
        select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
    )
    assert turn_count == 0

    # turn_number was claimed (incremented) before the crash — the gap is harmless.
    claimed = await db_session.scalar(
        select(Campaign.turn_number).where(Campaign.id == uuid.UUID(campaign_id))
    )
    assert claimed == 1


@pytest.mark.asyncio
async def test_provider_failure_returns_502_with_the_upstream_reason(auth_client, db_session):
    """An upstream failure is not our bug: it gets a 502 carrying the real reason,
    not the generic 500 that hid it (#50)."""
    campaign_id = await _create_campaign(auth_client)

    with patch(
        "app.api.turns.dm_graph.ainvoke",
        new=AsyncMock(
            side_effect=AIProviderError("local", "Rate limit exceeded: free-models-per-day")
        ),
    ):
        resp = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={"action": "do something"},
        )

    assert resp.status_code == 502
    assert "free-models-per-day" in resp.json()["detail"]

    turn_count = await db_session.scalar(
        select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
    )
    assert turn_count == 0


@pytest.mark.asyncio
async def test_action_on_missing_campaign_returns_404(auth_client):
    resp = await auth_client.post(
        f"/api/campaigns/{uuid.uuid4()}/action",
        json={"action": "do something"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Campaign not found"


@pytest.mark.asyncio
async def test_action_on_inactive_campaign_returns_400(auth_client, db_session):
    campaign_id = await _create_campaign(auth_client)
    campaign = await db_session.get(Campaign, uuid.UUID(campaign_id))
    campaign.status = CampaignStatus.COMPLETED
    await db_session.commit()

    resp = await auth_client.post(
        f"/api/campaigns/{campaign_id}/action",
        json={"action": "do something"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Campaign is not active"


@pytest.mark.asyncio
async def test_dice_results_are_flattened_into_dice_rolls(auth_client):
    """dice_results' per-roll dicts are merged into the legacy flat dice_rolls map."""
    campaign_id = await _create_campaign(auth_client)
    state = _fake_state(
        dice_results=[{"rolls": {"d20": 15}}, {"rolls": {"d6": 4}}],
    )

    with (
        patch("app.api.turns.dm_graph.ainvoke", new=AsyncMock(return_value=state)),
        patch("app.api.turns.compress_turn_to_summary", new=AsyncMock(return_value="summary")),
        patch("app.api.turns.generate_embedding", new=AsyncMock(return_value=[0.0] * 384)),
        patch("app.api.turns.extract_and_store_facts", new=AsyncMock(return_value=None)),
        patch("app.api.turns._background_compression", new=AsyncMock(return_value=None)),
        patch("app.api.turns._background_global_summary", new=AsyncMock(return_value=None)),
    ):
        resp = await auth_client.post(
            f"/api/campaigns/{campaign_id}/action",
            json={"action": "roll some dice"},
        )

    assert resp.status_code == 200
    assert resp.json()["dice_rolls"] == {"d20": 15, "d6": 4}


@pytest.mark.asyncio
async def test_background_compression_commits_then_returns():
    with patch("app.api.turns.ensure_compression", new=AsyncMock(return_value=None)) as inner:
        await _background_compression(uuid.uuid4(), 5)
    inner.assert_awaited_once()


@pytest.mark.asyncio
async def test_background_compression_swallows_errors():
    with patch(
        "app.api.turns.ensure_compression",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await _background_compression(uuid.uuid4(), 5)  # must not raise


@pytest.mark.asyncio
async def test_background_global_summary_commits_then_returns():
    with patch("app.api.turns.update_global_summary", new=AsyncMock(return_value=None)) as inner:
        await _background_global_summary(uuid.uuid4(), 10)
    inner.assert_awaited_once()


@pytest.mark.asyncio
async def test_background_global_summary_swallows_errors():
    with patch(
        "app.api.turns.update_global_summary",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await _background_global_summary(uuid.uuid4(), 10)  # must not raise
