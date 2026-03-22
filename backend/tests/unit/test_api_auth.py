import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models.user import User

client = TestClient(app)

# Helper to generate token
from jose import jwt


def create_mock_jwt(user_id: str):
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_register(mocker):
    mock_db = mocker.AsyncMock()

    class MockUserExistsResult:
        def scalar_one_or_none(self):
            return None  # User doesn't exist

    mock_db.execute.return_value = MockUserExistsResult()
    mock_db.commit = mocker.AsyncMock()
    mock_db.refresh = mocker.AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(
        "/api/auth/register",
        json={"username": "testuser", "email": "test@test.com", "password": "password"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    app.dependency_overrides.clear()


def test_login(mocker):
    mock_db = mocker.AsyncMock()
    
    # We need to test login, which involves fetching a User and verifying the password.
    # The password is hashed using Passlib (bcrypt). To mock it simply, we can patch verify_password.
    user_id = str(uuid.uuid4())
    user_mock = User(
        id=uuid.UUID(user_id),
        username="testuser",
        email="test@test.com",
        created_at=datetime.utcnow(),
    )
    user_mock.password_hash = "hashed_pw"

    class MockUserResult:
        def scalar_one_or_none(self):
            return user_mock

    mock_db.execute.return_value = MockUserResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Patch passlib verify
    mocker.patch("app.api.auth.verify_password", return_value=True)

    response = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "password"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    
    app.dependency_overrides.clear()


def test_login_invalid(mocker):
    mock_db = mocker.AsyncMock()
    
    class MockUserResult:
        def scalar_one_or_none(self):
            return None

    mock_db.execute.return_value = MockUserResult()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "password"},
    )
    assert response.status_code == 401

    app.dependency_overrides.clear()


def test_get_me(mocker):
    mock_db = mocker.AsyncMock()
    user_id = str(uuid.uuid4())
    user_mock = User(
        id=uuid.UUID(user_id),
        username="testuser",
        email="test@test.com",
        preferred_language="en",
        created_at=datetime.utcnow(),
    )

    async def override_get_current_user():
        return user_mock

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "testuser"

    app.dependency_overrides.clear()
