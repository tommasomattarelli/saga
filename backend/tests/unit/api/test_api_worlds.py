"""ADR 0008 S2 — GET /api/worlds lists the library."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_worlds_seeds_and_returns_example(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    response = client.get("/api/worlds")
    assert response.status_code == 200
    cards = response.json()
    assert cards[0]["slug"] == "the-awakening"
    assert cards[0]["name"] == "The Awakening"
    assert "content" not in cards[0]
