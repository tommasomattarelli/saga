"""ADR 0008 S2 — /api/worlds lists the library (seeded with the example World)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_worlds_returns_example(client: AsyncClient):
    response = await client.get("/api/worlds")
    assert response.status_code == 200
    worlds = response.json()

    slugs = [w["slug"] for w in worlds]
    assert "the-awakening" in slugs

    awakening = next(w for w in worlds if w["slug"] == "the-awakening")
    assert awakening["name"] == "The Awakening"
    assert awakening["author"] == "SAGA Team"
    assert "tutorial" in awakening["tags"]


@pytest.mark.asyncio
async def test_campaign_map_endpoint(auth_client):
    created = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Map Test",
            "death_mode": "destino",
            "character_data": {},
        },
    )
    campaign_id = created.json()["id"]

    resp = await auth_client.get(f"/api/campaigns/{campaign_id}/map")
    assert resp.status_code == 200
    data = resp.json()

    assert data["root"] in data["nodes"]
    assert data["player_position"] in data["nodes"]
    names = {n["name"] for n in data["nodes"].values()}
    assert {"Thornhaven", "Old Mines", "Shrine of First Light"} <= names
    assert any(e["mode"] == "foot" for e in data["edges"])
