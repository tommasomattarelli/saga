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


@pytest.mark.asyncio
async def test_editor_lifecycle(auth_client):
    # create
    created = await auth_client.post("/api/worlds", json={"name": "Mondo Editor", "author": "it"})
    assert created.status_code == 201
    slug = created.json()["slug"]
    assert slug == "mondo-editor"

    # read editable payload
    got = await auth_client.get(f"/api/worlds/{slug}")
    assert got.status_code == 200
    payload = got.json()
    assert payload["meta"]["name"] == "Mondo Editor"

    # edit + save
    payload["nodes"] = [
        {
            "slug": "prima-citta",
            "parent": None,
            "kind": "site",
            "name": "Prima Città",
            "position": {"x": 1, "y": 1},
        }
    ]
    saved = await auth_client.put(f"/api/worlds/{slug}", json=payload)
    assert saved.status_code == 200

    # invalid save rejected
    payload["nodes"].append({"slug": "rotto", "parent": None, "kind": "ghost-kind", "name": "X"})
    bad = await auth_client.put(f"/api/worlds/{slug}", json=payload)
    assert bad.status_code == 422

    # export
    exported = await auth_client.get(f"/api/worlds/{slug}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"

    # delete
    deleted = await auth_client.delete(f"/api/worlds/{slug}")
    assert deleted.status_code == 204
    listed = await auth_client.get("/api/worlds")
    assert slug not in [w["slug"] for w in listed.json()]
