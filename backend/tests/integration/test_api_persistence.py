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
        "difficulty": "medium",
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
        "difficulty": "hard",
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


@pytest.mark.asyncio
async def test_reading_a_campaign_migrates_the_world_state(auth_client, db_session):
    """A save that has not taken a turn since an upgrade must not reach the UI on the
    old shape — ADR 0003's v8 statblocks rendered as 0/0 life bars (2026-08-04)."""
    from sqlalchemy import select

    from app.models.campaign import Campaign

    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Stale Save",
            "difficulty": "medium",
            "character_data": {"name": "Eron", "hp": {"current": 10, "max": 10}},
        },
    )
    campaign_id = resp.json()["id"]

    # Rewind the stored overlay to the pre-statblock shape a real old save has.
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one()
    stale = dict(campaign.world_state)
    stale["meta"] = {**stale["meta"], "schema_version": 7}
    stale["npcs"] = {
        npc_id: {k: v for k, v in npc.items() if k not in {"hp", "max_hp", "defense"}}
        for npc_id, npc in stale["npcs"].items()
    }
    campaign.world_state = stale
    await db_session.commit()

    served = (await auth_client.get(f"/api/campaigns/{campaign_id}")).json()["world_state"]

    assert served["meta"]["schema_version"] == 8
    assert all(npc["max_hp"] > 0 for npc in served["npcs"].values())
