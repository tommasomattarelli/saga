from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from app.ai.providers.base import AIProvider, get_provider
from app.ai.router import (
    ModelConfig,
    get_instance_default,
    get_local_endpoints,
    get_user_generation,
)
from app.config import settings
from app.exceptions import ValidationError

type Generation = tuple[AIProvider, ModelConfig]

_owner: ContextVar[UUID | Generation | None] = ContextVar("generation_owner", default=None)


@contextmanager
def generation_context(owner: UUID | Generation) -> Iterator[None]:
    token = _owner.set(owner)
    try:
        yield
    finally:
        _owner.reset(token)


async def resolve_generation_context() -> Generation:
    owner = _owner.get()
    if owner is None:
        raise ValidationError("A user generation context is required.")
    if isinstance(owner, UUID):
        return await get_user_generation(owner)
    return owner


def operator_generation() -> Generation:
    config = get_instance_default()
    if config.provider == "local":
        base_url = get_local_endpoints().get(config.local_endpoint or "")
        if not base_url:
            raise ValidationError("Configure a named local endpoint for the instance default.")
        return get_provider("local", base_url=base_url), config
    key = {
        "openai": settings.openai_api_key,
        "openrouter": settings.openrouter_api_key,
        "google": settings.google_ai_api_key,
    }.get(config.provider)
    if not key:
        raise ValidationError(f"Configure the operator's key for `{config.provider}`.")
    return get_provider(config.provider, api_key=key), config
