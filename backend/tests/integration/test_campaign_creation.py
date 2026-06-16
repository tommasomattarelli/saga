"""Integration tests for campaign creation with template world initialization."""

import pytest


@pytest.mark.asyncio
async def test_create_campaign_seeds_world_state(auth_client, test_user):
    """Campaign creation seeds world_state from template."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "template_id": "tutorial",
            "name": "Test Campaign",
            "death_mode": "destino",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    world_state = data["world_state"]

    # NPCs seeded from template
    assert "Marta" in world_state["npcs"]
    marta = world_state["npcs"]["Marta"]
    assert marta["personality"] == "Warm but shrewd. Knows everyone's business."
    assert marta["role"] == "Tavern keeper"
    assert marta["disposition_toward_player"] == 0
    assert marta["last_interactions"] == []

    assert "Aldric" in world_state["npcs"]

    # Locations seeded
    assert "Thornhaven" in world_state["locations"]
    thornhaven = world_state["locations"]["Thornhaven"]
    assert "connections" in thornhaven
    assert "Forest Path" in thornhaven["connections"]

    assert "Shrine of First Light" in world_state["locations"]
    assert "Old Mines" in world_state["locations"]

    # Companions seeded
    assert "Lyra" in world_state["companions"]
    lyra = world_state["companions"]["Lyra"]
    assert lyra["stats"]["loyalty"] == 6

    # Factions seeded
    assert "The Hollow" in world_state["factions"]

    # Opening location set
    assert world_state["meta"]["current_location"] == "Shrine of First Light"
    assert world_state["meta"]["setting"] != ""

    # Time/weather from opening
    assert world_state["time_of_day"] == "morning"
    assert world_state["weather"] == "clear"

    # Schema v4 applied (migrate_world_state ran)
    assert world_state["meta"]["schema_version"] == 4
    assert world_state["clock"]["total_minutes"] == 480
    assert world_state["combat_state"]["active"] is False


@pytest.mark.asyncio
async def test_create_campaign_seeds_initial_quests(auth_client, test_user):
    """Campaign creation seeds initial_quests from template opening."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "template_id": "tutorial",
            "name": "Quest Seed Test",
            "death_mode": "destino",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    data = resp.json()

    quests = data["quests"]
    assert "active" in quests
    assert len(quests["active"]) == 1
    assert quests["active"][0]["name"] == "Who Am I?"


@pytest.mark.asyncio
async def test_create_campaign_unknown_template_returns_404(auth_client, test_user):
    """Creating a campaign with a non-existent template_id returns 404."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "template_id": "nonexistent_template_xyz",
            "name": "Bad Template",
            "death_mode": "destino",
            "character_data": {},
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
