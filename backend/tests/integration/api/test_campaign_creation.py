"""Integration tests for campaign creation from a library World (ADR 0008 S2)."""

import pytest

from app.memory.world_state import CURRENT_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_create_campaign_instantiates_world(auth_client, test_user):
    """Campaign creation freezes a baseline + seeds the overlay from scenario.yaml."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Test Campaign",
            "difficulty": "medium",
            "character_data": {"name": "Eron", "hp": 20, "max_hp": 20},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["world_slug"] == "the-awakening"

    world_state = data["world_state"]

    # NPCs uuid-keyed (ADR 0009 F1), seeded from npcs/ with UUID locations (J3)
    npc_names = {n["name"] for n in world_state["npcs"].values()}
    assert {"Marta", "Aldric", "Lyra"} <= npc_names
    marta = next(n for n in world_state["npcs"].values() if n["name"] == "Marta")
    assert marta["traits"]["personality"] == "Warm but shrewd. Knows everyone's business."
    assert marta["traits"]["role"] == "Tavern keeper"
    assert marta["slug"] == "marta"
    assert marta["lifecycle"] == "alive"
    assert marta["psychology"] == {"trust": 0, "respect": 0, "affection": 0, "fear": 0}
    assert marta["last_interactions"] == []

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
    assert world_state["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
    assert world_state["clock"]["total_minutes"] == 480
    assert "combat_state" not in world_state  # combat is not a mode (ADR 0003 B1)
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
            "difficulty": "medium",
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
            "difficulty": "medium",
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
            "difficulty": "medium",
            "character_data": {},
        },
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
