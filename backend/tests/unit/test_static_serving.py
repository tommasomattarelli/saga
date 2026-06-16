from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import app.config
from app.main import create_app


def _write_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root>SPA_INDEX</div>")
    (dist / "assets" / "app.js").write_text("APP_JS")
    return dist


@pytest.fixture
def served(tmp_path, monkeypatch):
    dist = _write_dist(tmp_path)
    monkeypatch.setattr(app.config.settings, "saga_frontend_dist", str(dist))
    application = create_app()
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://test")


async def test_serves_index_at_root(served):
    async with served as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    assert "SPA_INDEX" in r.text


async def test_serves_static_asset(served):
    async with served as ac:
        r = await ac.get("/assets/app.js")
    assert r.status_code == 200
    assert "APP_JS" in r.text


async def test_spa_fallback_for_unknown_path(served):
    async with served as ac:
        r = await ac.get("/campaigns/123/play")
    assert r.status_code == 200
    assert "SPA_INDEX" in r.text


async def test_does_not_shadow_existing_routes(served):
    async with served as ac:
        r = await ac.get("/openapi.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")


async def test_no_mount_when_unset(monkeypatch):
    monkeypatch.setattr(app.config.settings, "saga_frontend_dist", "")
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        r = await ac.get("/")
    assert r.status_code == 404
