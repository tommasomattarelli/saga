from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
from uuid import UUID

from app.ai.providers.base import AIProvider
from app.ai.providers.local import LocalProvider

_campaign: ContextVar[UUID | None] = ContextVar("generation_campaign", default=None)


@contextmanager
def campaign_session(campaign_id: UUID) -> Iterator[None]:
    token = _campaign.set(campaign_id)
    try:
        yield
    finally:
        _campaign.reset(token)


def campaign_provider(provider: AIProvider) -> AIProvider:
    campaign_id = _campaign.get()
    if campaign_id is None:
        return provider
    if not isinstance(provider, LocalProvider):
        raise ValueError("OpenRouter session affinity requires an OpenRouter-compatible client.")
    isolated = copy(provider)
    # Copies share their HTTP transport; only the resolved request's headers are scoped.
    isolated.client = provider.client.with_options(
        default_headers={"x-session-id": str(campaign_id)}
    )
    return isolated
