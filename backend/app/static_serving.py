from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.config import settings


class _SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def mount_frontend(app: FastAPI) -> None:
    # Guarded so dev and Docker (Vite dev server) are untouched; mounted last so
    # /api and FastAPI's own routes keep precedence over the catch-all.
    if not settings.saga_frontend_dist:
        return
    dist_path = Path(settings.saga_frontend_dist)
    if not (dist_path / "index.html").is_file():
        return
    app.mount("/", _SPAStaticFiles(directory=dist_path, html=True), name="frontend")
