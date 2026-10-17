from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.credentials import (
    credential_source,
    effective_embedding_provider,
    effective_generation_provider,
    has_personal_key,
)
from app.ai.router import PROVIDER_NAMES, get_allowed_providers, get_local_endpoints
from app.dependencies import get_db
from app.models.user import User
from app.schemas.settings import ApiKeysUpdate, SettingsPatch
from app.security.auth import get_current_user
from app.security.encryption import encrypt_api_key

router = APIRouter()

# The minimal settings UI (ADR 0018, point 6) is built on these endpoints.


def _settings_payload(user: User) -> dict:
    provider = effective_generation_provider(user)
    return {
        "preferred_language": user.preferred_language,
        "generation_provider": user.generation_provider,
        "generation_model": user.generation_model,
        "generation_local_endpoint": user.generation_local_endpoint,
        "embedding_provider": user.embedding_provider,
        "embedding_model": user.embedding_model,
        "embedding_local_endpoint": user.embedding_local_endpoint,
        "server_key_consents": user.server_key_consents or {},
        "has_openai_key": has_personal_key(user, "openai"),
        "has_openrouter_key": has_personal_key(user, "openrouter"),
        "has_google_key": has_personal_key(user, "google"),
        "effective_provider": provider,
        "credential_source": credential_source(user, provider),
        "effective_embedding_provider": effective_embedding_provider(user),
        "embedding_credential_source": credential_source(user, effective_embedding_provider(user)),
    }


@router.get("")
async def get_settings(user: User = Depends(get_current_user)) -> dict:
    """Get current user settings and the effective credential provenance."""
    return _settings_payload(user)


@router.patch("")
async def update_settings(
    updates: SettingsPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    fields = updates.model_dump(exclude_unset=True)

    if fields.get("preferred_language"):
        user.preferred_language = fields["preferred_language"]

    for prefix in ("generation", "embedding"):
        provider = fields.get(f"{prefix}_provider")
        if provider and (
            provider not in PROVIDER_NAMES or provider not in get_allowed_providers()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provider `{provider}` is not enabled on this instance",
            )
        endpoint = fields.get(f"{prefix}_local_endpoint")
        if endpoint and endpoint not in get_local_endpoints():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Local endpoint `{endpoint}` is not configured on this instance",
            )
    for field, value in fields.items():
        if field != "preferred_language":
            setattr(user, field, (value or "").strip() or None)

    await db.commit()
    return _settings_payload(user)


@router.put("/api-keys")
async def update_api_keys(
    keys: ApiKeysUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if keys.anthropic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The direct Anthropic provider was removed; select OpenRouter explicitly.",
        )

    if keys.openai:
        user.openai_api_key_enc = encrypt_api_key(keys.openai)
    if keys.openrouter:
        user.openrouter_api_key_enc = encrypt_api_key(keys.openrouter)
    if keys.google:
        user.google_api_key_enc = encrypt_api_key(keys.google)
    await db.commit()
    return {"message": "API keys updated"}


@router.put("/server-key-consents")
async def update_server_key_consents(
    consents: dict[str, bool],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    allowed = set(get_allowed_providers())
    unknown = sorted(set(consents) - allowed)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider not enabled on this instance: " + ", ".join(unknown),
        )
    merged = dict(user.server_key_consents or {})
    merged.update({provider: bool(enabled) for provider, enabled in consents.items()})
    user.server_key_consents = merged
    await db.commit()
    return {"message": "Server key consents updated", "server_key_consents": merged}
