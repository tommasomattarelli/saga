from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, campaigns, characters, export, journal, saves, templates, websocket
from app.api import settings as settings_api
from app.dependencies import close_db, close_redis, init_db, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await init_redis()
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAGA",
        description="AI-Driven Tabletop RPG",
        version="0.1.0",
        lifespan=lifespan,
    )

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
    app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
    app.include_router(saves.router, prefix="/api/saves", tags=["saves"])
    app.include_router(journal.router, prefix="/api/journal", tags=["journal"])
    app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
    app.include_router(export.router, prefix="/api/export", tags=["export"])
    app.include_router(websocket.router, prefix="/api/ws", tags=["websocket"])

    return app


app = create_app()
