import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app
from app.models.campaign import Campaign
from app.models.save import Save

client = TestClient(app)


@pytest.fixture
def mock_user_dependency(mocker):
    mock_user = mocker.Mock()
    mock_user.id = uuid.uuid4()

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def test_list_saves(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    campaign_id = str(uuid.uuid4())

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return Campaign()  # Campaign exists

    class MockSavesResult:
        def scalars(self):
            class MockAll:
                def all(self):
                    save_mock = Save(
                        id=uuid.uuid4(),
                        campaign_id=uuid.UUID(campaign_id),
                        name="AutoSave",
                        turn_number=1,
                        scene_summary="Summary",
                        is_auto=True,
                        created_at=datetime.now(UTC),
                    )
                    return [save_mock]

            return MockAll()

    mock_db.execute.side_effect = [MockCampaignResult(), MockSavesResult()]

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.get(f"/api/saves/{campaign_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "AutoSave"

    app.dependency_overrides.clear()


def test_create_save_not_found(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    campaign_id = str(uuid.uuid4())

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return None

    mock_db.execute.return_value = MockCampaignResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(f"/api/saves/{campaign_id}", json={"name": "My Save"})
    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_create_save(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mock_db.add = mocker.Mock()
    campaign_id = str(uuid.uuid4())
    camp_mock = Campaign(id=uuid.UUID(campaign_id), world_state={"time": "day"})

    class MockCampaignResult:
        def scalar_one_or_none(self):
            return camp_mock

    mock_db.execute.return_value = MockCampaignResult()
    mock_db.commit = mocker.AsyncMock()

    async def mock_refresh(obj):
        obj.id = uuid.uuid4()
        obj.turn_number = 1
        obj.scene_summary = "Summary"
        obj.is_auto = False
        obj.created_at = datetime.now(UTC)

    mock_db.refresh = mocker.AsyncMock(side_effect=mock_refresh)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(f"/api/saves/{campaign_id}", json={"name": "My Save"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Save"
    assert data["campaign_id"] == campaign_id
    assert mock_db.add.called
    mock_db.commit.assert_awaited()

    app.dependency_overrides.clear()
