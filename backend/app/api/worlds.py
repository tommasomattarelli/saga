from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.core.world_library import ensure_library, list_worlds
from app.models.user import User
from app.security.auth import get_current_user
from app.services import world_service

router = APIRouter()


@router.get("")
async def get_worlds() -> list[dict]:
    """List the Worlds available in the library (ADR 0008 C9)."""
    ensure_library()
    return list_worlds()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_world(body: dict, user: User = Depends(get_current_user)) -> dict:
    """Create a new World from the default taxonomy (ADR 0008 I7)."""
    return world_service.create_world(body)


@router.get("/{slug}")
async def get_world(slug: str, user: User = Depends(get_current_user)) -> dict:
    """Full editable payload for the editor (ADR 0008 I7)."""
    return world_service.get_editable_world(slug)


@router.put("/{slug}")
async def save_world(slug: str, body: dict, user: User = Depends(get_current_user)) -> dict:
    """Validate + persist + git-commit the whole world (ADR 0008 I6)."""
    return world_service.save_world(slug, body)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_world(slug: str, user: User = Depends(get_current_user)) -> None:
    world_service.delete_world(slug)


@router.get("/{slug}/export")
async def export_world(slug: str, user: User = Depends(get_current_user)) -> Response:
    """Download the world as a zip (ADR 0008 C10)."""
    data = world_service.export_world(slug)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_world(
    file: UploadFile = File(...), user: User = Depends(get_current_user)
) -> dict:
    """Upload a world zip: validate before placement (ADR 0008 C10)."""
    return world_service.import_world(await file.read())
