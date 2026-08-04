import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app
from app.models.campaign import Campaign, CampaignStatus, Difficulty

client = TestClient(app)


@pytest.fixture
def mock_user_dependency(mocker):
    mock_user = mocker.Mock()
    mock_user.id = uuid.uuid4()
    mock_user.openai_api_key_enc = b"enc"

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def test_list_campaigns(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()

    class MockResult:
        def scalars(self):
            class MockAll:
                def all(self):
                    return [
                        Campaign(
                            id=uuid.uuid4(),
                            name="Test Campaign",
                            user_id=mock_user_dependency.id,
                            world_slug="fantasy",
                            status=CampaignStatus.ACTIVE,
                            difficulty=Difficulty.HARD,
                            turn_number=1,
                            character_data={},
                            world_state={},
                            quests={},
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    ]

            return MockAll()

    mock_db.execute.return_value = MockResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get("/api/campaigns")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Test Campaign"

    app.dependency_overrides.clear()


def test_create_campaign(mocker, mock_user_dependency, tmp_path, monkeypatch):
    # Campaigns are instantiated from a library World (ADR 0008) — point the
    # library at a tmp home; ensure_library seeds the bundled example World.
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))

    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    mock_db.commit = mocker.AsyncMock()

    async def mock_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(UTC)
        obj.updated_at = datetime.now(UTC)
        if not hasattr(obj, "status") or obj.status is None:
            obj.status = CampaignStatus.ACTIVE
        if not hasattr(obj, "turn_number") or obj.turn_number is None:
            obj.turn_number = 0

    mock_db.refresh = mocker.AsyncMock(side_effect=mock_refresh)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    create_data = {
        "name": "My New Game",
        "world_id": "the-awakening",
        "difficulty": "hard",
        "character_data": {"name": "Hero"},
    }
    response = client.post("/api/campaigns", json=create_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My New Game"
    assert data["world_slug"] == "the-awakening"
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_get_campaign(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    camp_id = str(uuid.uuid4())

    camp = Campaign(
        id=uuid.UUID(camp_id),
        name="Test Campaign",
        user_id=mock_user_dependency.id,
        world_slug="fantasy",
        status=CampaignStatus.ACTIVE,
        difficulty=Difficulty.HARD,
        turn_number=1,
        character_data={},
        world_state={},
        quests={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/campaigns/{camp_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Campaign"

    app.dependency_overrides.clear()


def test_update_status(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    camp_id = str(uuid.uuid4())

    camp = Campaign(
        id=uuid.UUID(camp_id),
        user_id=mock_user_dependency.id,
        name="Test Campaign",
        world_slug="fantasy",
        status=CampaignStatus.ACTIVE,
        difficulty=Difficulty.HARD,
        turn_number=1,
        character_data={},
        world_state={},
        quests={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp

    mock_db.execute.return_value = MockCampaignResult()
    mock_db.commit = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.patch(f"/api/campaigns/{camp_id}/status?new_status=abandoned")
    assert response.status_code == 200
    assert response.json()["status"] == "abandoned"
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_post_action(mocker, mock_user_dependency):
    """Test the new REST POST /action endpoint (replaces WebSocket + /turn)."""
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    mock_db.commit = mocker.AsyncMock()
    mock_db.execute = mocker.AsyncMock()
    camp_id = str(uuid.uuid4())

    camp = Campaign(
        id=uuid.UUID(camp_id),
        user_id=mock_user_dependency.id,
        name="Test Campaign",
        world_slug="fantasy",
        status=CampaignStatus.ACTIVE,
        difficulty=Difficulty.HARD,
        turn_number=1,
        character_data={"name": "Hero", "hp": {"current": 10, "max": 10}},
        world_state={},
        quests={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp

        def scalar_one(self):
            # Used only by the atomic turn-number claim (UPDATE ... RETURNING).
            return 2

    mock_db.execute.return_value = MockCampaignResult()

    @asynccontextmanager
    async def fake_db_ctx():
        yield mock_db

    mocker.patch("app.api.turns.get_db_context", side_effect=fake_db_ctx)

    # Mock dm_graph.ainvoke to avoid real LLM calls
    fake_state = {
        "narration": "You take a step forward.",
        "narration_segments": None,
        "dice_results": [],
        "npc_dialogues": [],
        "world_state": {},
        "char_data": {"name": "Hero", "hp": {"current": 10, "max": 10}},
        "scene_mood": "neutral",
        "tool_events": [],
        "death_event": None,
        "model_used": "gpt-4o",
        "importance_score": 5,
        "time_passed_minutes": 0,
    }
    mocker.patch("app.api.turns.dm_graph.ainvoke", return_value=fake_state)
    mocker.patch("app.api.turns.compress_turn_to_summary", return_value="A step forward.")
    mocker.patch("app.api.turns.generate_embedding", return_value=[0.1] * 1536)
    mocker.patch("app.api.turns.extract_and_store_facts")
    mocker.patch("app.api.turns._background_compression")

    response = client.post(f"/api/campaigns/{camp_id}/action", json={"action": "Walk forward"})
    assert response.status_code == 200
    data = response.json()
    assert data["turn_number"] == 2
    assert "You take a step" in data["narration"]

    app.dependency_overrides.clear()
