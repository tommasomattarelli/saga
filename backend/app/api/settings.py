

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.user import User
from app.security.auth import get_current_user
from app.security.encryption import encrypt_api_key

router = APIRouter()


@router.get("")
async def get_settings(user: User = Depends(get_current_user)) -> dict:
    """Get current user settings."""
    return {
        "preferred_language": user.preferred_language,
        "has_openai_key": bool(user.openai_api_key_enc),
        "has_anthropic_key": bool(user.anthropic_api_key_enc),
        "has_google_key": bool(user.google_api_key_enc),
    }


@router.patch("")
async def update_settings(
    updates: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:

    if "preferred_language" in updates:
        user.preferred_language = updates["preferred_language"]
    await db.commit()
    return {"message": "Settings updated"}


@router.put("/api-keys")
async def update_api_keys(
    keys: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:

    if "openai" in keys and keys["openai"]:
        user.openai_api_key_enc = encrypt_api_key(keys["openai"])
    if "anthropic" in keys and keys["anthropic"]:
        user.anthropic_api_key_enc = encrypt_api_key(keys["anthropic"])
    if "google" in keys and keys["google"]:
        user.google_api_key_enc = encrypt_api_key(keys["google"])
    await db.commit()
    return {"message": "API keys updated"}
