import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.turn import Turn

client = TestClient(app)


@pytest.fixture
def mock_user_dependency(mocker):
    mock_user = mocker.Mock()
    mock_user.id = uuid.uuid4()

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def test_export_campaign(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    campaign_id = str(uuid.uuid4())

    camp_mock = Campaign(
        id=uuid.UUID(campaign_id),
        name="Epic Quest",
        world_state={"locations": {}},
        character_data={"hp": 10},
    )

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp_mock

    class MockTurnsResult:
        def scalars(self):
            class MockAll:
                def all(self):
                    return [
                        Turn(
                            turn_number=1, player_action="Go", narration="You go."
                        )
                    ]

            return MockAll()

    mock_db.execute.side_effect = [MockCampaignResult(), MockTurnsResult()]

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["campaign"]["name"] == "Epic Quest"
    assert len(data["turns"]) == 1
    assert data["turns"][0]["player_action"] == "Go"

    app.dependency_overrides.clear()


def test_export_campaign_not_found(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    campaign_id = str(uuid.uuid4())

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return None

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/export/{campaign_id}")
    assert response.status_code == 404

    app.dependency_overrides.clear()
