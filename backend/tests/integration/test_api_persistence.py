import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.campaign import Campaign


@pytest.mark.asyncio
async def test_create_and_get_campaign_persistence(auth_client: AsyncClient, db_session):
    """Verify that a created campaign is actually saved in the DB."""
    # 1. Create Campaign
    create_data = {
        "name": "Integration Test Story",
        "world_id": "the-awakening",
        "death_mode": "destino",
        "character_data": {"name": "Valerius", "class": "Paladin"},
    }
    response = await auth_client.post("/api/campaigns", json=create_data)
    assert response.status_code == 201
    campaign_id = response.json()["id"]

    # 2. Verify in DB directly (No Mocking!)
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    db_campaign = result.scalar_one_or_none()

    assert db_campaign is not None
    assert db_campaign.name == "Integration Test Story"
    assert db_campaign.character_data["name"] == "Valerius"

    # 3. Get via API
    get_response = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Integration Test Story"


@pytest.mark.asyncio
async def test_campaign_status_update_persistence(auth_client: AsyncClient, db_session):
    """Verify that updating a campaign status persists."""
    # 1. Create
    create_data = {
        "name": "Status Test",
        "world_id": "the-awakening",
        "death_mode": "ironman",
        "character_data": {"name": "Test"},
    }
    response = await auth_client.post("/api/campaigns", json=create_data)
    campaign_id = response.json()["id"]

    # 2. Update Status
    update_response = await auth_client.patch(
        f"/api/campaigns/{campaign_id}/status?new_status=abandoned"
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "abandoned"

    # 3. Verify in DB
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    db_campaign = result.scalar_one_or_none()
    assert db_campaign.status.value == "abandoned"
