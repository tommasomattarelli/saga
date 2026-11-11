from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.ai.router import validate_embedding_config, validate_generation_config
from app.api import (
    auth,
    campaigns,
    characters,
    embedding_index,
    export,
    journal,
    memory,
    runtime_config,
    saves,
    turns,
    worlds,
)
from app.api import settings as settings_api
from app.api.rate_limit import limiter, rate_limit_exceeded_handler
from app.config import settings
from app.core.action_policy import get_action_policy
from app.dependencies import close_db, init_db
from app.logging_setup import setup_logging
from app.memory.embedding_lifecycle import recover_interrupted_rebuilds
from app.memory.embedding_worker import start_embedding_worker, stop_embedding_worker
from app.memory.job_lifecycle import start_memory_worker, stop_memory_worker
from app.memory.production_policy import configured_memory_policy
from app.static_serving import mount_frontend

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_generation_config()
    validate_embedding_config()
    configured_memory_policy()
    get_action_policy()
    await init_db()
    await recover_interrupted_rebuilds()
    start_embedding_worker()
    start_memory_worker()
    yield
    await stop_memory_worker()
    await stop_embedding_worker()
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAGA",
        description="AI-Driven Tabletop RPG",
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
    app.include_router(characters.router, prefix="/api/characters", tags=["characters"])
    app.include_router(worlds.router, prefix="/api/worlds", tags=["worlds"])
    app.include_router(saves.router, prefix="/api/saves", tags=["saves"])
    app.include_router(journal.router, prefix="/api/journal", tags=["journal"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])
    app.include_router(turns.router, prefix="/api/campaigns", tags=["turns"])
    app.include_router(memory.router, prefix="/api/campaigns", tags=["memory"])
    app.include_router(runtime_config.router, prefix="/api", tags=["config"])
    app.include_router(embedding_index.router, prefix="/api/campaigns", tags=["embedding-index"])

    mount_frontend(app)

    return app


app = create_app()
