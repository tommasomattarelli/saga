import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app
from app.models.campaign import Campaign, CampaignStatus, DeathMode
from app.models.template import Template

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
                            template_id="fantasy",
                            status=CampaignStatus.ACTIVE,
                            death_mode=DeathMode.IRONMAN,
                            turn_number=1,
                            character_data={},
                            world_state={},
                            quests={},
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
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


def test_create_campaign(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()

    # Needs to find a template
    templ = Template(
        slug="fantasy",
        name="Fantasy",
        description="test",
        difficulty=3,
        tags=["fantasy"],
        content={
            "initial_system_prompt": "prompt",
            "initial_campaign_context": "context",
            "initial_world_state": {},
            "encounters": {},
        },
    )

    class MockTemplateResult:
        def scalar_one_or_none(self):
            return templ

    mock_db.execute.return_value = MockTemplateResult()
    mock_db.commit = mocker.AsyncMock()

    async def mock_refresh(obj):
        obj.id = uuid.uuid4()
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = datetime.now(timezone.utc)
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
        "template_id": "fantasy",
        "death_mode": "ironman",
        "character_data": {"name": "Hero"},
    }
    response = client.post("/api/campaigns", json=create_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My New Game"
    assert data["template_id"] == "fantasy"
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
        template_id="fantasy",
        status=CampaignStatus.ACTIVE,
        death_mode=DeathMode.IRONMAN,
        turn_number=1,
        character_data={},
        world_state={},
        quests={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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
        template_id="fantasy",
        status=CampaignStatus.ACTIVE,
        death_mode=DeathMode.IRONMAN,
        turn_number=1,
        character_data={},
        world_state={},
        quests={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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


def test_post_turn(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    camp_id = str(uuid.uuid4())

    camp = Campaign(
        id=uuid.UUID(camp_id),
        user_id=mock_user_dependency.id,
        name="Test Campaign",
        template_id="fantasy",
        status=CampaignStatus.ACTIVE,
        death_mode=DeathMode.IRONMAN,
        turn_number=1,
        character_data={},
        world_state={},
        quests={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    from app.models.turn import Turn

    fake_turn = Turn(
        id=uuid.uuid4(),
        campaign_id=camp.id,
        turn_number=2,
        player_action="Walk forward",
        narration="You take a step.",
        model_used="gpt-4o",
        created_at=datetime.now(timezone.utc),
    )

    # Mock process_turn
    mocker.patch("app.api.campaigns.process_turn", return_value=fake_turn)

    response = client.post(f"/api/campaigns/{camp_id}/turn", json={"action": "Walk forward"})
    assert response.status_code == 200
    data = response.json()
    assert data["turn_number"] == 2

    app.dependency_overrides.clear()
