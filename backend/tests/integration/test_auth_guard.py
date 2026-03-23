import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(client: AsyncClient):
    """Verify that an unauthenticated request returns 401."""
    response = await client.get("/api/campaigns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_is_rejected(client: AsyncClient):
    """Verify that a malformed JWT is rejected."""
    client.headers["Authorization"] = "Bearer totally.invalid.token"
    response = await client.get("/api/campaigns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_rejected(client: AsyncClient):
    """Verify that an expired JWT is rejected."""
    from datetime import UTC, datetime, timedelta
    from jose import jwt
    from app.config import settings

    expired_payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "type": "access",
    }
    expired_token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    client.headers["Authorization"] = f"Bearer {expired_token}"
    response = await client.get("/api/campaigns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_with_nonexistent_user_is_rejected(client: AsyncClient):
    """Verify that a valid JWT for a deleted user returns 401."""
    import uuid
    from app.security.auth import create_access_token

    ghost_user_id = uuid.uuid4()
    token = create_access_token(ghost_user_id)
    client.headers["Authorization"] = f"Bearer {token}"
    response = await client.get("/api/campaigns")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_user_can_access_campaigns(auth_client: AsyncClient):
    """Verify that a real authenticated user can access the campaigns endpoint."""
    response = await auth_client.get("/api/campaigns")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
