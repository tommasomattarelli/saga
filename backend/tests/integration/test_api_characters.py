import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.campaign import Campaign


@pytest.mark.asyncio
async def test_get_and_update_character_in_campaign(auth_client: AsyncClient, db_session):
    """Verify that character data within a campaign can be retrieved and updated."""
    # 1. Create Campaign (which includes character_data)
    char_data = {
        "name": "Eldrin",
        "char_class": "Wizard",
        "stats": {"int": 18}
    }
    create_resp = await auth_client.post("/api/campaigns", json={
        "name": "Character Test",
        "template_id": "tutorial",
        "death_mode": "destino",
        "character_data": char_data
    })
    campaign_id = create_resp.json()["id"]

    # 2. Get Character via API
    get_resp = await auth_client.get(f"/api/characters/{campaign_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Eldrin"

    # 3. Update Character via API
    update_data = {"name": "Eldrin the Great", "level": 2}
    patch_resp = await auth_client.patch(f"/api/characters/{campaign_id}", json=update_data)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Eldrin the Great"

    # 4. Verify in DB
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    db_campaign = result.scalar_one()
    assert db_campaign.character_data["name"] == "Eldrin the Great"
