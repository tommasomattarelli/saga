"""Request schemas for the per-user settings endpoints (ADR 0018 A3/A4)."""

from __future__ import annotations

from pydantic import BaseModel


class SettingsPatch(BaseModel):
    preferred_language: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    generation_local_endpoint: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_local_endpoint: str | None = None


class ApiKeysUpdate(BaseModel):
    openai: str | None = None
    openrouter: str | None = None
    google: str | None = None
    anthropic: str | None = None
