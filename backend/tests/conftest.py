import os
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.dependencies
from app.dependencies import get_redis
from app.main import app as fastapi_app
from app.models.base import Base
from app.models.user import User
from app.security.auth import create_access_token

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test"
)
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6380/0")

# Session scoped engine with NullPool for isolation
engine = create_async_engine(DATABASE_URL, echo=False, poolclass=NullPool)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Override dependencies globally before any tests run
app.dependencies.engine = engine
app.dependencies.async_session = async_session_factory


# Disable lifespan
async def noop():
    pass


app.dependencies.init_db = noop
app.dependencies.init_redis = noop
app.dependencies.close_db = noop
app.dependencies.close_redis = noop


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    from app.dependencies import seed_templates

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_templates()
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database():
    """Clean all tables except templates before each test."""
    async with engine.begin() as conn:
        # Get all table names
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' AND tablename != 'templates';"
            )
        )
        tables = [row[0] for row in result.fetchall()]
        if tables:
            await conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE;"))
    yield


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Test session (no external transaction, real commits)."""
    async with async_session_factory() as session:
        yield session
        await session.close()


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    # Clean redis
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture
async def client(redis_client: Redis) -> AsyncIterator[AsyncClient]:
    """API client with its own session handling."""

    # We do NOT override get_db here, we let the app use its own async_session_factory
    # which we already overrode globally to point to our test engine.
    async def override_get_redis():
        return redis_client

    fastapi_app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> dict:
    u_id = uuid.uuid4()
    user = User(
        id=u_id,
        username=f"test_{u_id.hex[:8]}",
        email=f"test_{u_id.hex[:8]}@example.com",
        hashed_password="hashed_password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()  # Real commit

    token = create_access_token(u_id)
    return {"user": user, "token": token}


@pytest.fixture
async def auth_client(client: AsyncClient, test_user: dict) -> AsyncClient:
    client.headers["Authorization"] = f"Bearer {test_user['token']}"
    return client
