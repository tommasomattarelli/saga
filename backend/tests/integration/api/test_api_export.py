"""Export integration tests — JSON schema and ownership guard."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.memory.job_retention import cleanup_terminal_generation_payloads
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.turn import Turn
from tests.integration.memory.storage_support import (
    HistoryFixture,
    production_policy,
)
from tests.integration.memory.test_job_publication import _claimed_job


@pytest.mark.asyncio
async def test_export_empty_campaign(auth_client: AsyncClient, db_session):
    """Export of a campaign with no turns should return valid JSON with empty turns list."""
    camp_resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Export Test",
            "world_id": "the-awakening",
            "difficulty": "medium",
            "character_data": {"name": "Tester", "hp": 10},
        },
    )
    campaign_id = camp_resp.json()["id"]

    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one()
    campaign.world_state = {**campaign.world_state, "relations": [{"kind": "ally"}]}
    await db_session.commit()

    resp = await auth_client.get(f"/api/export/{campaign_id}")
    assert resp.status_code == 200

    data = resp.json()
    # Top-level schema
    assert "campaign" in data
    assert "turns" in data
    assert isinstance(data["turns"], list)
    assert len(data["turns"]) == 0

    # Campaign fields
    camp = data["campaign"]
    assert camp["name"] == "Export Test"
    assert camp["character_data"]["hp"] == 10
    assert "world_state" in camp
    assert camp["world_state"]["relations"] == [{"kind": "ally"}]
    assert "the-hollow" in camp["world_state"]["factions"]
    assert "quests" in camp


@pytest.mark.asyncio
async def test_export_campaign_with_turns(auth_client: AsyncClient, db_session):
    """Export should include all turns with correct fields."""
    camp_resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Story Export",
            "world_id": "the-awakening",
            "difficulty": "medium",
            "character_data": {},
        },
    )
    campaign_id = camp_resp.json()["id"]

    # Insert turns directly
    for i in range(1, 4):
        db_session.add(
            Turn(
                campaign_id=campaign_id,
                turn_number=i,
                player_action=f"Action {i}",
                narration=f"Narration {i}",
                model_used="gpt-4o",
                importance_score=5,
            )
        )
    await db_session.commit()

    resp = await auth_client.get(f"/api/export/{campaign_id}")
    assert resp.status_code == 200
    data = resp.json()

    turns = data["turns"]
    assert len(turns) == 3
    assert turns[0]["turn_number"] == 1
    assert turns[0]["player_action"] == "Action 1"
    assert turns[2]["narration"] == "Narration 3"


@pytest.mark.asyncio
async def test_export_forbidden_for_other_user(
    auth_client: AsyncClient, client: AsyncClient, db_session
):
    """Verify that a user cannot export another user's campaign."""
    import uuid

    from app.models.user import User
    from app.security.auth import create_access_token

    # User A creates campaign
    camp_resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Private Camp",
            "world_id": "the-awakening",
            "difficulty": "medium",
            "character_data": {},
        },
    )
    campaign_id = camp_resp.json()["id"]

    # User B token
    user_b_id = uuid.uuid4()
    user_b = User(
        id=user_b_id, username="exporter_b", email="export_b@test.dev", hashed_password="x"
    )
    db_session.add(user_b)
    await db_session.commit()
    token_b = create_access_token(user_b_id)
    client.headers["Authorization"] = f"Bearer {token_b}"

    # User B tries to export User A's campaign
    resp = await client.get(f"/api/export/{campaign_id}")
    assert resp.status_code == 404


async def test_campaign_export_omits_raw_generation_payloads_before_and_after_cleanup(
    auth_client: AsyncClient,
    db_session,
    test_user,
) -> None:
    campaign = Campaign(
        user_id=test_user["user"].id,
        world_slug="test",
        name="Payload export",
        difficulty=Difficulty.MEDIUM,
    )
    db_session.add(campaign)
    await db_session.flush()
    payload = production_policy()
    policy = MemoryPolicy(
        campaign_id=campaign.id,
        schema_version=1,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(campaign_id=campaign.id)
    db_session.add_all([policy, root])
    await db_session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await db_session.commit()
    fixture = HistoryFixture(db_session, campaign, policy, root)
    job, _, generations, _, _ = await _claimed_job(fixture)
    if campaign.active_head_turn_id is not None:
        from app.models.turn import Turn

        head = await db_session.get(Turn, campaign.active_head_turn_id)
        assert head is not None
        campaign.turn_number = head.turn_number
    candidates = tuple(generation.raw_candidate for generation in generations)
    job.state = "succeeded"
    job.claim_token = None
    job.lease_expires_at = None
    job.terminal_at = datetime.now(UTC) - timedelta(days=1)
    await fixture.session.commit()

    before = await auth_client.get(f"/api/export/{fixture.campaign.id}")
    assert before.status_code == 200
    before_payload = json.dumps(before.json())
    for candidate in candidates:
        assert candidate is not None and candidate not in before_payload
    assert not {"raw_candidate", "receipt", "request_identity_snapshot"} & set(
        before.json()["generations"][0]
    )

    assert await cleanup_terminal_generation_payloads(
        fixture.session, fixture.campaign.id, retention_days=1
    ) == len(generations)
    await fixture.session.commit()
    after = await auth_client.get(f"/api/export/{fixture.campaign.id}")
    assert after.status_code == 200
    after_payload = json.dumps(after.json())
    for candidate in candidates:
        assert candidate is not None and candidate not in after_payload
    assert job.state == "succeeded"
