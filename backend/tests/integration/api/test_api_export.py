"""Export integration tests — JSON schema and ownership guard."""

import pytest
from httpx import AsyncClient

from app.models.turn import Turn


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
