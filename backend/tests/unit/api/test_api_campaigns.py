import uuid
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
    mock_user.generation_provider = "local"
    mock_user.generation_model = "test-model"
    mock_user.generation_local_endpoint = "ollama"

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
                            language="en",
                            user_id=mock_user_dependency.id,
                            world_slug="fantasy",
                            status=CampaignStatus.ACTIVE,
                            difficulty=Difficulty.HARD,
                            turn_number=1,
                            context_epoch=0,
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
        language="en",
        user_id=mock_user_dependency.id,
        world_slug="fantasy",
        status=CampaignStatus.ACTIVE,
        difficulty=Difficulty.HARD,
        turn_number=1,
        context_epoch=0,
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


def test_post_action_requires_idempotency_and_context_fields(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    claim = mocker.patch("app.api.turns.claim_action", new=mocker.AsyncMock())

    response = client.post(
        f"/api/campaigns/{uuid.uuid4()}/action", json={"action": "Walk forward"}
    )

    assert response.status_code == 422
    claim.assert_not_awaited()
    app.dependency_overrides.clear()
