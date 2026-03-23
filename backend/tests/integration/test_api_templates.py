import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_templates_from_seed(client: AsyncClient):
    """Verify that templates seeded in conftest.py are returned by the API."""
    response = await client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()

    # We expect at least the default templates (tutorial, survival - slug is last_light, etc)
    slugs = [t["slug"] for t in templates]
    assert "tutorial" in slugs
    assert "last_light" in slugs

    # Check one in detail
    tutorial = next(t for t in templates if t["slug"] == "tutorial")
    assert tutorial["name"] == "The Awakening"
    assert tutorial["author"] == "SAGA Team"


@pytest.mark.asyncio
async def test_get_single_template_detail(client: AsyncClient):
    """Verify that getting a specific template returns the full content."""
    response = await client.get("/api/templates/last_light")
    assert response.status_code == 200
    template = response.json()

    assert template["slug"] == "last_light"
    assert "content" in template
    # Template content top-level keys: world, opening, story_arcs
    assert "world" in template["content"]
