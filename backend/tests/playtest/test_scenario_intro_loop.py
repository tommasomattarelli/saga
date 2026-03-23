"""Playtest: Intro Loop scenario.

Simulates: Register -> Login -> Create Campaign -> 3 API calls.
Verifies the happy path works end-to-end with a real database.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus


@pytest.mark.asyncio
async def test_register_login_create_campaign(client: AsyncClient, db_session: AsyncSession):
    """Full lifecycle: register a user, authenticate, create a campaign, and verify state."""
    # --- 1. Register ---
    register_payload = {
        "username": "hero_player",
        "email": "hero@saga.dev",
        "password": "strong-password-123",
    }
    reg_response = await client.post("/api/auth/register", json=register_payload)
    assert reg_response.status_code in (200, 201), f"Registration failed: {reg_response.text}"

    # --- 2. Login ---
    login_payload = {"username": "hero_player", "password": "strong-password-123"}
    login_response = await client.post("/api/auth/login", json=login_payload)
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"
    token = login_response.json()["access_token"]

    # --- 3. Create Campaign ---
    client.headers["Authorization"] = f"Bearer {token}"
    campaign_payload = {
        "name": "The Awakening Playtest",
        "template_id": "tutorial",
        "death_mode": "destino",
        "character_data": {"name": "Aria", "class": "Ranger"},
    }
    camp_response = await client.post("/api/campaigns", json=campaign_payload)
    assert camp_response.status_code == 201, f"Campaign creation failed: {camp_response.text}"
    campaign_id = camp_response.json()["id"]

    # --- 4. Verify campaign in DB ---
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    db_campaign = result.scalar_one_or_none()
    assert db_campaign is not None
    assert db_campaign.name == "The Awakening Playtest"
    assert db_campaign.status == CampaignStatus.ACTIVE
    assert db_campaign.character_data["name"] == "Aria"

    # --- 5. List campaigns (should be exactly 1) ---
    list_response = await client.get("/api/campaigns")
    assert list_response.status_code == 200
    campaigns = list_response.json()
    assert len(campaigns) == 1
    assert campaigns[0]["id"] == campaign_id

    # --- 6. Get single campaign ---
    get_response = await client.get(f"/api/campaigns/{campaign_id}")
    assert get_response.status_code == 200
    assert get_response.json()["template_id"] == "tutorial"


@pytest.mark.asyncio
async def test_user_isolation(client: AsyncClient, db_session: AsyncSession):
    """Verify that User A cannot see User B's campaigns."""
    # Create User A
    reg_a = await client.post(
        "/api/auth/register",
        json={
            "username": "user_a",
            "email": "a@saga.dev",
            "password": "pass-a-123",
        },
    )
    assert reg_a.status_code in (200, 201)
    login_a = await client.post(
        "/api/auth/login", json={"username": "user_a", "password": "pass-a-123"}
    )
    token_a = login_a.json()["access_token"]

    # Create User B
    reg_b = await client.post(
        "/api/auth/register",
        json={
            "username": "user_b",
            "email": "b@saga.dev",
            "password": "pass-b-123",
        },
    )
    assert reg_b.status_code in (200, 201)
    login_b = await client.post(
        "/api/auth/login", json={"username": "user_b", "password": "pass-b-123"}
    )
    token_b = login_b.json()["access_token"]

    # User A creates a campaign
    client.headers["Authorization"] = f"Bearer {token_a}"
    await client.post(
        "/api/campaigns",
        json={
            "name": "A's Secret Quest",
            "template_id": "tutorial",
            "death_mode": "ironman",
            "character_data": {"name": "Solo"},
        },
    )

    # User B should see 0 campaigns
    client.headers["Authorization"] = f"Bearer {token_b}"
    list_b = await client.get("/api/campaigns")
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0, "User B should not see User A's campaigns"
