"""Per-user provider credentials and consent resolution (ADR 0018 A3/A4)."""

from __future__ import annotations

from app.ai.router import get_instance_default, get_server_key_fallback
from app.config import settings
from app.config_loader import load_saga_config
from app.models.user import User

_PERSONAL_KEY_FIELDS = {
    "openai": "openai_api_key_enc",
    "openrouter": "openrouter_api_key_enc",
    "google": "google_api_key_enc",
}

_SERVER_KEY_SETTINGS = {
    "openai": "openai_api_key",
    "openrouter": "openrouter_api_key",
    "google": "google_ai_api_key",
}


def effective_generation_provider(user: User | None) -> str:
    """The provider a user's calls run on: personal choice or instance default (A6)."""
    if user is not None and user.generation_provider:
        return str(user.generation_provider)
    return get_instance_default().provider


def effective_embedding_provider(user: User) -> str:
    if user.embedding_provider:
        return str(user.embedding_provider)
    return str(load_saga_config().get("embedding", {}).get("default", {}).get("provider", ""))


def has_personal_key(user: User, provider: str) -> bool:
    field = _PERSONAL_KEY_FIELDS.get(provider)
    if field is None:
        return False
    return bool(getattr(user, field, None))


def user_consents_server_key(user: User, provider: str) -> bool:
    consents = user.server_key_consents or {}
    return bool(consents.get(provider, False))


def server_key_present(provider: str) -> bool:
    field = _SERVER_KEY_SETTINGS.get(provider)
    if field is None:
        return False
    return bool(getattr(settings, field, ""))


def credential_source(user: User, provider: str) -> str:
    """personal | server | missing — the provenance the UI shows (ADR 0018 A4)."""
    if provider == "local":
        return "not_required"
    if has_personal_key(user, provider):
        return "personal"
    if (
        user_consents_server_key(user, provider)
        and get_server_key_fallback().get(provider, False)
        and server_key_present(provider)
    ):
        return "server"
    return "missing"
