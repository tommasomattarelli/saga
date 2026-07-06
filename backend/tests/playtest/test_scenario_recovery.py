"""Playtest: Save/Load Recovery Scenario.

Flow: Create Campaign -> Save -> Damage Character -> Load Save -> Verify full restoration.
This tests the complete state machine of the save/load system against a real DB.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.save import Save


@pytest.mark.asyncio
async def test_scenario_save_load_recovery(auth_client: AsyncClient, db_session):
    """Full recovery scenario: save, damage, load, verify restored state."""
    # 1. Start Campaign
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Recovery Run",
            "world_id": "the-awakening",
            "death_mode": "destino",
            "character_data": {"name": "Aldric", "hp": 30, "max_hp": 30, "level": 5},
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]
    assert resp.json()["character_data"]["hp"] == 30

    # 2. Create Save at max HP
    save_resp = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Full Power"})
    assert save_resp.status_code == 201
    save_id = save_resp.json()["id"]

    # Verify snapshot captured the right HP
    result = await db_session.execute(select(Save).where(Save.id == save_id))
    db_save = result.scalar_one()
    assert db_save.campaign_snapshot["character_data"]["hp"] == 30

    # 3. Simulate battle damage via PATCH /characters
    patch_resp = await auth_client.patch(f"/api/characters/{campaign_id}", json={"hp": 5})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["hp"] == 5

    # 4. Load Save
    load_resp = await auth_client.post(f"/api/saves/{campaign_id}/load/{save_id}")
    assert load_resp.status_code == 200

    # 5. Verify full restoration via GET campaign
    get_resp = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert get_resp.status_code == 200
    restored = get_resp.json()
    assert restored["character_data"]["hp"] == 30
    assert restored["character_data"]["level"] == 5


@pytest.mark.asyncio
async def test_scenario_multiple_save_slots(auth_client: AsyncClient, db_session):
    """Verify multiple save slots coexist and can be loaded independently."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "MultiSave Camp",
            "world_id": "the-awakening",
            "death_mode": "destino",
            "character_data": {"hp": 20},
        },
    )
    campaign_id = resp.json()["id"]

    # Save slot 1 — hp:20
    save1 = await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Slot 1"})
    save1_id = save1.json()["id"]

    # Damage, then save slot 2 — hp:8
    await auth_client.patch(f"/api/characters/{campaign_id}", json={"hp": 8})
    await auth_client.post(f"/api/saves/{campaign_id}", json={"name": "Slot 2"})

    # List should show 2 saves
    list_resp = await auth_client.get(f"/api/saves/{campaign_id}")
    assert len(list_resp.json()) == 2

    # Load slot 1 (hp:20)
    await auth_client.post(f"/api/saves/{campaign_id}/load/{save1_id}")
    get_resp = await auth_client.get(f"/api/campaigns/{campaign_id}")
    assert get_resp.json()["character_data"]["hp"] == 20
