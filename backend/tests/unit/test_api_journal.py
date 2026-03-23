import uuid
from datetime import datetime, timezone

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


def test_get_journal(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    campaign_id = str(uuid.uuid4())

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return Campaign()  # Campaign exists

    class MockTurnsResult:
        def scalars(self):
            class MockAll:
                def all(self):
                    turn_mock = Turn(
                        id=uuid.uuid4(),
                        turn_number=1,
                        player_action="Walked",
                        narration="You walked.",
                        summary="Summary",
                        created_at=datetime.now(timezone.utc),
                    )
                    return [turn_mock]

            return MockAll()

    mock_db.execute.side_effect = [MockCampaignResult(), MockTurnsResult()]

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/journal/{campaign_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["turn_number"] == 1
    assert data[0]["player_action"] == "Walked"

    app.dependency_overrides.clear()


def test_get_journal_campaign_not_found(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    campaign_id = str(uuid.uuid4())

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return None  # Campaign does not exist

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/journal/{campaign_id}")
    assert response.status_code == 404

    app.dependency_overrides.clear()
