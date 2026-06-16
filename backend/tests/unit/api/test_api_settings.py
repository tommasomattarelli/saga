import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.dependencies import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_user_dependency(mocker):
    mock_user = mocker.Mock()
    mock_user.id = uuid.uuid4()
    mock_user.preferred_language = "en"
    mock_user.openai_api_key_enc = b"encrypted_key"
    mock_user.anthropic_api_key_enc = None
    mock_user.google_ai_api_key_enc = None

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def test_get_settings(mock_user_dependency):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["preferred_language"] == "en"
    assert data["has_openai_key"] is True
    assert data["has_anthropic_key"] is False


def test_update_settings(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.patch("/api/settings", json={"preferred_language": "it"})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Settings updated"

    # User preferred_language should be updated
    assert mock_user_dependency.preferred_language == "it"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_update_api_keys(mocker, mock_user_dependency):
    mock_db = mocker.AsyncMock()
    mocker.patch("app.api.settings.encrypt_api_key", return_value=b"new_encrypted_key")

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.put(
        "/api/settings/api-keys", json={"openai": "sk-12345", "anthropic": "", "google": ""}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "API keys updated"

    assert mock_user_dependency.openai_api_key_enc == b"new_encrypted_key"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()
