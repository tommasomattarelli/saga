"""Request schemas for the per-user settings endpoints (ADR 0018 A3/A4)."""

from __future__ import annotations

from pydantic import BaseModel, StrictBool, field_validator


class SettingsPatch(BaseModel):
    preferred_language: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    generation_local_endpoint: str | None = None
    generation_allow_json_mode_fallback: StrictBool | None = None
    generation_allow_prompt_only_fallback: StrictBool | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_local_endpoint: str | None = None

    @field_validator(
        "generation_allow_json_mode_fallback",
        "generation_allow_prompt_only_fallback",
        mode="before",
    )
    @classmethod
    def require_explicit_boolean(cls, value: object) -> object:
        if value is None:
            raise ValueError("A boolean value is required")
        return value


class ApiKeysUpdate(BaseModel):
    openai: str | None = None
    openrouter: str | None = None
    google: str | None = None
    anthropic: str | None = None


class ProfileDefaults(BaseModel):
    """The instance default a user inherits before configuring their own profile."""

    provider: str
    model: str
    local_endpoint: str | None = None


class SettingsPolicy(BaseModel):
    """Read-only instance policy the settings UI needs to render its choices.

    Local endpoints are NAMES only — the backend never exposes the URLs a user
    may point at, and no key material or ciphertext is carried here.
    """

    allowed_providers: list[str]
    local_endpoints: list[str]
    generation_default: ProfileDefaults
    embedding_default: ProfileDefaults
    server_key_sharing: dict[str, bool]
