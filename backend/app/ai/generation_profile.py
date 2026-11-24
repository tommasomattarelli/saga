"""Effective structured-generation settings for a user's current destination."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.ai.destination_identity import destination_fingerprint
from app.ai.providers.google_destination import resolve_google_destination
from app.ai.router import (
    PROVIDER_NAMES,
    get_allowed_providers,
    get_instance_default,
    get_local_endpoints,
)
from app.config_loader import load_saga_config
from app.models.user import User


@dataclass(frozen=True)
class GenerationFormatSettings:
    allow_json_mode_fallback: bool
    allow_prompt_only_fallback: bool
    destination_fingerprint: str | None


@dataclass(frozen=True)
class GenerationDestination:
    provider: str
    model: str
    endpoint: str
    mode: str | None = None


def resolve_generation_destination(user: User | None) -> GenerationDestination | None:
    default = get_instance_default()
    if user is not None and bool(user.generation_provider) != bool(user.generation_model):
        return None
    provider = str((user.generation_provider if user else None) or default.provider)
    model = str((user.generation_model if user else None) or default.model).strip()
    if provider not in PROVIDER_NAMES or provider not in get_allowed_providers() or not model:
        return None
    if provider == "local":
        endpoint_name = (
            user.generation_local_endpoint if user and user.generation_provider else None
        )
        if not user or not user.generation_provider:
            endpoint_name = default.local_endpoint
        endpoint = get_local_endpoints().get(endpoint_name or "")
        if not endpoint:
            return None
        return GenerationDestination(provider, model, endpoint)
    if provider == "openai":
        endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        mode = None
    elif provider == "openrouter":
        endpoint = "https://openrouter.ai/api/v1"
        mode = None
    else:
        google_destination = resolve_google_destination()
        endpoint = google_destination.effective_url
        mode = google_destination.mode
    return GenerationDestination(provider, model, endpoint, mode)


def resolve_generation_format_settings(user: User | None) -> GenerationFormatSettings:
    destination = resolve_generation_destination(user)
    fingerprint = None
    if destination is not None:
        fingerprint = destination_fingerprint(
            provider=destination.provider,
            model=destination.model,
            endpoint=destination.endpoint,
            mode=destination.mode,
        )
    generation = load_saga_config().get("generation", {})
    defaults = {
        "json": generation.get("allow_json_mode_fallback", False),
        "prompt": generation.get("allow_prompt_only_fallback", False),
    }
    if any(not isinstance(value, bool) for value in defaults.values()):
        raise ValueError("generation fallback defaults must be booleans")
    bound = (
        user is not None
        and user.generation_format_fingerprint == fingerprint
        and fingerprint is not None
    )
    json_override = (
        user.generation_allow_json_mode_fallback if bound and user is not None else None
    )
    prompt_override = (
        user.generation_allow_prompt_only_fallback if bound and user is not None else None
    )
    return GenerationFormatSettings(
        allow_json_mode_fallback=(
            json_override if json_override is not None else defaults["json"]
        ),
        allow_prompt_only_fallback=(
            prompt_override if prompt_override is not None else defaults["prompt"]
        ),
        destination_fingerprint=fingerprint,
    )
