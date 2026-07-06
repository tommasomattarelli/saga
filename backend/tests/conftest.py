import os
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.dependencies
from app.main import app as fastapi_app
from app.models.base import Base
from app.models.user import User
from app.security.auth import create_access_token

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test"
)

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
app.dependencies.close_db = noop


@pytest.fixture(scope="session", autouse=True)
async def setup_database(tmp_path_factory):
    # World library in a throwaway home (ADR 0008 C9) — ensure_library seeds
    # the bundled example World on first use.
    os.environ["SAGA_HOME"] = str(tmp_path_factory.mktemp("saga-home"))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database():
    """Clean all tables before each test."""
    async with engine.begin() as conn:
        # Get all table names
        result = await conn.execute(
            text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';")
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
async def client() -> AsyncIterator[AsyncClient]:
    """API client with its own session handling.

    We do NOT override get_db here; the app uses its own async_session_factory
    which we already overrode globally to point to our test engine.
    """
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
