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
    mock_user.openrouter_api_key_enc = None
    mock_user.google_api_key_enc = None
    mock_user.generation_provider = None
    mock_user.generation_model = None
    mock_user.generation_local_endpoint = None
    mock_user.embedding_provider = None
    mock_user.embedding_model = None
    mock_user.embedding_local_endpoint = None
    mock_user.server_key_consents = None

    async def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    return mock_user


def _override_db(mocker):
    mock_db = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return mock_db


def test_get_settings(mock_user_dependency):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["preferred_language"] == "en"
    assert data["has_openai_key"] is True
    assert data["has_openrouter_key"] is False
    assert data["has_google_key"] is False
    assert data["generation_provider"] is None
    assert data["generation_model"] is None
    assert data["server_key_consents"] == {}
    assert data["effective_provider"] == "google"
    assert data["credential_source"] == "missing"
    assert "has_anthropic_key" not in data


def test_update_settings(mocker, mock_user_dependency):
    mock_db = _override_db(mocker)

    response = client.patch("/api/settings", json={"preferred_language": "it"})
    assert response.status_code == 200
    data = response.json()
    assert data["preferred_language"] == "it"

    assert mock_user_dependency.preferred_language == "it"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_patch_generation_config(mocker, mock_user_dependency):
    mock_db = _override_db(mocker)

    response = client.patch(
        "/api/settings",
        json={"generation_provider": "openrouter", "generation_model": "nvidia/whatever"},
    )
    assert response.status_code == 200
    assert mock_user_dependency.generation_provider == "openrouter"
    assert mock_user_dependency.generation_model == "nvidia/whatever"
    data = response.json()
    assert data["effective_provider"] == "openrouter"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_patch_generation_provider_must_be_allowed(mocker, mock_user_dependency):
    _override_db(mocker)

    response = client.patch("/api/settings", json={"generation_provider": "cohere"})
    assert response.status_code == 400
    assert "not enabled" in response.json()["detail"]

    app.dependency_overrides.clear()


def test_patch_can_reset_generation_to_inherit(mocker, mock_user_dependency):
    mock_user_dependency.generation_provider = "openai"
    mock_user_dependency.generation_model = "gpt-x"
    _override_db(mocker)

    response = client.patch(
        "/api/settings", json={"generation_provider": None, "generation_model": None}
    )
    assert response.status_code == 200
    assert mock_user_dependency.generation_provider is None
    assert mock_user_dependency.generation_model is None

    app.dependency_overrides.clear()


def test_update_api_keys(mocker, mock_user_dependency):
    mock_db = _override_db(mocker)
    mocker.patch("app.api.settings.encrypt_api_key", return_value=b"new_encrypted_key")

    response = client.put("/api/settings/api-keys", json={"openai": "sk-12345", "google": ""})
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "API keys updated"

    assert mock_user_dependency.openai_api_key_enc == b"new_encrypted_key"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_update_openrouter_key(mocker, mock_user_dependency):
    mock_db = _override_db(mocker)
    mocker.patch("app.api.settings.encrypt_api_key", return_value=b"router-cipher")

    response = client.put("/api/settings/api-keys", json={"openrouter": "sk-or-1"})
    assert response.status_code == 200
    assert mock_user_dependency.openrouter_api_key_enc == b"router-cipher"
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_anthropic_key_is_rejected(mocker, mock_user_dependency):
    _override_db(mocker)

    response = client.put("/api/settings/api-keys", json={"anthropic": "sk-ant"})
    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_server_consents_merge(mocker, mock_user_dependency):
    mock_db = _override_db(mocker)

    response = client.put("/api/settings/server-key-consents", json={"openai": True})
    assert response.status_code == 200
    assert mock_user_dependency.server_key_consents == {"openai": True}
    assert response.json()["server_key_consents"] == {"openai": True}
    mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


def test_server_consents_reject_unknown_provider(mocker, mock_user_dependency):
    _override_db(mocker)

    response = client.put("/api/settings/server-key-consents", json={"cohere": True})
    assert response.status_code == 400

    app.dependency_overrides.clear()
