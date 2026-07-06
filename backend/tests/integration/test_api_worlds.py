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
