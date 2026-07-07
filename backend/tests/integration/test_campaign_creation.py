"""Integration tests for campaign creation from a library World (ADR 0008 S2)."""

import pytest


@pytest.mark.asyncio
async def test_create_campaign_instantiates_world(auth_client, test_user):
    """Campaign creation freezes a baseline + seeds the overlay from scenario.yaml."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Test Campaign",
            "death_mode": "destino",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["world_slug"] == "the-awakening"

    world_state = data["world_state"]

    # NPCs seeded from npcs/ with UUID locations (J3)
    marta = world_state["npcs"]["Marta"]
    assert marta["personality"] == "Warm but shrewd. Knows everyone's business."
    assert marta["role"] == "Tavern keeper"
    assert marta["psychology"] == {"trust": 0, "respect": 0, "affection": 0, "fear": 0}
    assert marta["last_interactions"] == []
    assert "Aldric" in world_state["npcs"]
    assert "Lyra" in world_state["npcs"]

    # Player starts at the scenario start_location, addressed by UUID
    start = world_state["player_position"]
    assert start == world_state["meta"]["current_location"]
    assert marta["location"] != start  # Marta is in Thornhaven, not at the shrine

    # Factions seeded
    assert "The Hollow" in world_state["factions"]

    # Opening seeds time/weather/narration
    assert world_state["time_of_day"] == "morning"
    assert world_state["weather"] == "clear"
    assert "canopy of ancient oaks" in world_state["meta"]["opening_narration"]

    # Schema v5 overlay containers
    assert world_state["meta"]["schema_version"] == 6
    assert world_state["clock"]["total_minutes"] == 480
    assert world_state["combat_state"]["active"] is False
    assert world_state["node_status"] == {}
    assert world_state["edge_overrides"] == []


@pytest.mark.asyncio
async def test_create_campaign_freezes_baseline(auth_client, test_user, db_session):
    """The static authored tree lands in world_baseline, referenced by UUID (C7/C11)."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Baseline Test",
            "death_mode": "destino",
            "character_data": {},
        },
    )
    assert resp.status_code == 201

    from sqlalchemy import select

    from app.models.campaign import Campaign

    result = await db_session.execute(select(Campaign))
    campaign = result.scalars().first()
    baseline = campaign.world_baseline

    assert campaign.world_version == "1.0.0"
    assert baseline["source_world"] == "the-awakening"
    shrine_id = baseline["slug_map"]["shrine-of-first-light"]
    assert baseline["nodes"][shrine_id]["name"] == "Shrine of First Light"
    # Edges reference UUIDs, never slugs (A6)
    edge = baseline["edges"]["forest-path"]
    assert edge["from"] in baseline["nodes"]
    assert edge["to"] in baseline["nodes"]


@pytest.mark.asyncio
async def test_create_campaign_seeds_initial_quests(auth_client, test_user):
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Quest Seed Test",
            "death_mode": "destino",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    quests = resp.json()["quests"]
    assert len(quests["active"]) == 1
    assert quests["active"][0]["name"] == "Who Am I?"


@pytest.mark.asyncio
async def test_create_campaign_unknown_world_returns_404(auth_client, test_user):
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "nonexistent-world-xyz",
            "name": "Bad World",
            "death_mode": "destino",
            "character_data": {},
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
