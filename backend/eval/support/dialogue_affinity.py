import json
from copy import copy
from uuid import NAMESPACE_URL, uuid5

from app.ai.providers.base import AIProvider
from app.ai.providers.local import LocalProvider


def session_id_for_model(checkpoint: str, model: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(["saga-eval", checkpoint, model])))


def provider_with_session(provider: AIProvider, session_id: str | None) -> AIProvider:
    if session_id is None:
        return provider
    if not isinstance(provider, LocalProvider):
        raise ValueError("Evaluation session affinity requires an OpenRouter-compatible client.")
    isolated = copy(provider)
    isolated.client = provider.client.with_options(
        default_headers={"x-session-id": session_id}, max_retries=0
    )
    return isolated
