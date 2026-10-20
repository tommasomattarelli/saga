"""Per-user provider credentials and consent resolution (ADR 0018 A3/A4/B1)."""

from __future__ import annotations

from cryptography.exceptions import InvalidTag

from app.ai.embedding_config import (
    EmbeddingCredential,
    EmbeddingSpace,
    ResolvedEmbedding,
    build_space,
    check_space_contract,
    get_embedding_default_space,
    get_embedding_policy,
    local_space,
)
from app.ai.router import (
    PROVIDER_NAMES,
    ModelConfig,
    get_allowed_providers,
    get_instance_default,
    get_local_endpoints,
    get_server_key_fallback,
)
from app.config import settings
from app.config_loader import load_saga_config
from app.exceptions import ValidationError
from app.models.user import User
from app.security.encryption import decrypt_api_key

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


def _hosted_key(user: User, provider: str) -> str:
    """Plaintext key for a hosted provider under the A4 order: personal, consented server."""
    source = credential_source(user, provider)
    if source == "personal":
        try:
            key = decrypt_api_key(getattr(user, _PERSONAL_KEY_FIELDS[provider]))
        except (InvalidTag, ValueError) as exc:
            raise ValidationError(
                f"The personal key for `{provider}` cannot be read; enter it again in settings."
            ) from exc
        if not key.strip():
            raise ValidationError(f"The personal key for `{provider}` is empty; enter it again.")
        return key
    if source == "server":
        return str(getattr(settings, _SERVER_KEY_SETTINGS[provider]))
    raise ValidationError(
        f"Add a personal key for `{provider}` or enable consented server-key sharing in settings."
    )


def resolve_generation(user: User) -> tuple[ModelConfig, str | None, str | None]:
    default = get_instance_default()
    if bool(user.generation_provider) != bool(user.generation_model):
        raise ValidationError("Choose both a generation provider and a model.")
    provider = str(user.generation_provider or default.provider)
    model = str(user.generation_model or default.model).strip()
    if provider not in PROVIDER_NAMES or provider not in get_allowed_providers():
        raise ValidationError(f"Provider `{provider}` is not enabled on this instance.")
    if not model:
        raise ValidationError("Choose a generation model in settings.")
    config = ModelConfig(provider=provider, model=model, max_tokens=default.max_tokens)
    if provider == "local":
        endpoint = (
            user.generation_local_endpoint if user.generation_provider else default.local_endpoint
        )
        base_url = get_local_endpoints().get(endpoint or "")
        if not base_url:
            raise ValidationError("Choose a configured local endpoint in settings.")
        return config, None, base_url

    return config, _hosted_key(user, provider), None


def _profile_space(user: User) -> EmbeddingSpace:
    """The space the user's own embedding profile names (or the instance default)."""
    if bool(user.embedding_provider) != bool(user.embedding_model):
        raise ValidationError("Choose both an embedding provider and a model.")
    default = get_embedding_default_space()
    provider = str(user.embedding_provider or default.provider)
    model = str(user.embedding_model or default.model).strip()
    if not model:
        raise ValidationError("Choose an embedding model in settings.")
    if provider == "local":
        endpoint_name = user.embedding_local_endpoint or default.endpoint_name
        if not endpoint_name:
            raise ValidationError("Choose a configured local embedding endpoint in settings.")
        return local_space(str(endpoint_name), model)
    return build_space(provider, model)


def _credential_for(user: User, space: EmbeddingSpace) -> EmbeddingCredential:
    """Provenance for ONE call, re-derived every time (never persisted)."""
    if space.provider == "local":
        return EmbeddingCredential(key=None, source="not_required")
    source = credential_source(user, space.provider)
    return EmbeddingCredential(key=_hosted_key(user, space.provider), source=source)


def resolve_embedding(user: User, space: EmbeddingSpace | None = None) -> ResolvedEmbedding:
    """Embedding profile independent of generation (B1): own provider/model/credential.

    A stored-space manifest pins the space FOREVER: its provider/model/endpoint
    are never replaced by the user's current profile, and its endpoint (name and
    URL) is revalidated against the instance policy today — a snapshot the
    policy no longer authorizes fails fast instead of silently reusing it.
    """
    policy = get_embedding_policy()
    space = space if space is not None else _profile_space(user)
    check_space_contract(space)
    return ResolvedEmbedding(space=space, credential=_credential_for(user, space), policy=policy)
