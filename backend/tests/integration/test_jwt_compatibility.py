import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.security.auth import decode_token, hash_password

SECRET = "saga-jwt-upgrade-compatibility-secret-32-bytes"
USER_ID = "11111111-1111-4111-8111-111111111111"
LEGACY_ACCESS = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMTExMTExMS0xMTExLTQxMTEtODExMS0xMTExMTExMTExMTEiLCJleHAiOjQxMDI0NDQ4MDAsInR5cGUiOiJhY2Nlc3MifQ."
    "QJyJvjRySFL3qCXlKkm5OxZGbBr4hgQhgqLTP0KOhp0"
)
LEGACY_REFRESH = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMTExMTExMS0xMTExLTQxMTEtODExMS0xMTExMTExMTExMTEiLCJleHAiOjQxMDI0NDQ4MDAsInR5cGUiOiJyZWZyZXNoIn0."
    "qMlA_QgFEg_nFm8kypR9TF4ahTJXsDh8vTDzzmWLr1c"
)


@pytest.fixture(autouse=True)
def legacy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")


@pytest.fixture
async def legacy_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.UUID(USER_ID),
        username="legacy-user",
        email="legacy@example.com",
        hashed_password=hash_password("compatibility-password"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


def assert_legacy_compatible(token: str, token_type: str, user_id: str = USER_ID) -> None:
    header, payload, signature = token.split(".")
    expected = hmac.new(SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    assert hmac.compare_digest(base64.urlsafe_b64decode(signature + "=="), expected)
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assert claims["sub"] == user_id
    assert claims["type"] == token_type
    assert claims["exp"] > datetime.now(UTC).timestamp()


async def test_pre_upgrade_access_token_authenticates_existing_user(
    client: AsyncClient, legacy_user: User
) -> None:
    response = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {LEGACY_ACCESS}"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(legacy_user.id)


async def test_pre_upgrade_refresh_token_issues_legacy_compatible_tokens(
    client: AsyncClient, legacy_user: User
) -> None:
    response = await client.post("/api/auth/refresh", json={"refresh_token": LEGACY_REFRESH})

    assert response.status_code == 200
    assert_legacy_compatible(response.json()["access_token"], "access")
    assert_legacy_compatible(response.json()["refresh_token"], "refresh")


async def test_login_keeps_token_format(client: AsyncClient, legacy_user: User) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": legacy_user.username, "password": "compatibility-password"},
    )

    assert response.status_code == 200
    assert_legacy_compatible(response.json()["access_token"], "access")
    assert_legacy_compatible(response.json()["refresh_token"], "refresh")


async def test_registration_keeps_token_format(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "username": "registered-user",
            "email": "registered@example.com",
            "password": "compatibility-password",
        },
    )

    assert response.status_code == 201
    tokens = response.json()
    profile = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert profile.status_code == 200
    user_id = profile.json()["id"]
    assert_legacy_compatible(tokens["access_token"], "access", user_id)
    assert_legacy_compatible(tokens["refresh_token"], "refresh", user_id)


@pytest.mark.parametrize(
    "token",
    [
        LEGACY_REFRESH,
        LEGACY_ACCESS.rsplit(".", 1)[0] + ".invalid-signature",
        "eyJhbGciOiJub25lIn0.eyJzdWIiOiJmb3JnZWQifQ.",
    ],
)
async def test_invalid_access_credentials_return_401(client: AsyncClient, token: str) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_access_token_cannot_refresh(client: AsyncClient) -> None:
    response = await client.post("/api/auth/refresh", json={"refresh_token": LEGACY_ACCESS})

    assert response.status_code == 401


def test_pre_upgrade_claims_are_preserved() -> None:
    assert decode_token(LEGACY_ACCESS) == {"sub": USER_ID, "exp": 4102444800, "type": "access"}
