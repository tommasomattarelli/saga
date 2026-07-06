from fastapi import APIRouter

from app.core.world_library import ensure_library, list_worlds

router = APIRouter()


@router.get("")
async def get_worlds() -> list[dict]:
    """List the Worlds available in the library (ADR 0008 C9)."""
    ensure_library()
    return list_worlds()
