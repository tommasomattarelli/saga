"""FastAPI dependency injection."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from redis.asyncio import Redis

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: Redis | None = None


async def init_db() -> None:
    """Initialize the database engine."""
    from app.models.base import Base  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close the database engine."""
    await engine.dispose()


async def init_redis() -> None:
    """Initialize Redis connection."""
    global redis_client
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    """Close Redis connection."""
    if redis_client:
        await redis_client.aclose()


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a database session."""
    async with async_session() as session:
        yield session


def get_db_context():
    """Return an async context manager for a database session"""
    return async_session()


async def get_redis() -> Redis:
    """Return the Redis client."""
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client
