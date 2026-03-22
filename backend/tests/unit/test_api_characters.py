import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app
from app.models.campaign import Campaign

client = TestClient(app)


@pytest.fixture
def mock_user_dependency(mocker):
    mock_user = mocker.Mock()
    mock_user.id = uuid.uuid4()

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def test_get_characters(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    campaign_id = str(uuid.uuid4())

    camp_mock = Campaign(
        id=uuid.UUID(campaign_id),
        character_data={"hp": 15, "max_hp": 20, "name": "Bord"}
    )
    camp_mock.created_at = datetime.utcnow()

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp_mock

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/characters/{campaign_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Bord"

    app.dependency_overrides.clear()


def test_update_characters(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    campaign_id = str(uuid.uuid4())

    camp_mock = Campaign(
        id=uuid.UUID(campaign_id),
        character_data={"hp": 15, "max_hp": 20, "name": "Bord"}
    )
    camp_mock.created_at = datetime.utcnow()

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp_mock

    mock_db.execute.return_value = MockCampaignResult()
    mock_db.commit = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.patch(
        f"/api/characters/{campaign_id}",
        json={"character_data": {"hp": 12, "name": "Bord"}}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["character_data"]["hp"] == 12
    assert mock_db.commit.called

    app.dependency_overrides.clear()
