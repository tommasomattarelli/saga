"""Unit tests for per-user credential resolution (ADR 0018 A3/A4)."""

from __future__ import annotations

from unittest.mock import Mock

from app.ai.credentials import (
    credential_source,
    effective_generation_provider,
    has_personal_key,
)
from app.config import settings


def _user(**overrides) -> Mock:
    user = Mock()
    user.generation_provider = None
    user.openai_api_key_enc = None
    user.openrouter_api_key_enc = None
    user.google_api_key_enc = None
    user.server_key_consents = None
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


class TestEffectiveProvider:
    def test_falls_back_to_instance_default(self):
        assert effective_generation_provider(_user()) == "google"
        assert effective_generation_provider(None) == "google"

    def test_user_choice_wins(self):
        user = _user(generation_provider="openrouter")
        assert effective_generation_provider(user) == "openrouter"


class TestPersonalKeys:
    def test_presence_comes_from_the_encrypted_column(self):
        assert has_personal_key(_user(openai_api_key_enc="cipher"), "openai") is True
        assert has_personal_key(_user(), "openai") is False

    def test_local_and_unknown_providers_have_no_key(self):
        assert has_personal_key(_user(), "local") is False
        assert has_personal_key(_user(), "nope") is False


class TestCredentialSource:
    def test_personal_key_wins(self):
        assert credential_source(_user(openai_api_key_enc="cipher"), "openai") == "personal"

    def test_server_key_requires_both_consents(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_api_key", "server-key")
        monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openai": True})
        assert credential_source(_user(), "openai") == "missing"
        consented = _user(server_key_consents={"openai": True})
        assert credential_source(consented, "openai") == "server"

    def test_operator_flag_off_keeps_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_api_key", "server-key")
        monkeypatch.setattr(
            "app.ai.credentials.get_server_key_fallback", lambda: {"openai": False}
        )
        consented = _user(server_key_consents={"openai": True})
        assert credential_source(consented, "openai") == "missing"

    def test_absent_server_key_keeps_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_api_key", "")
        monkeypatch.setattr("app.ai.credentials.get_server_key_fallback", lambda: {"openai": True})
        consented = _user(server_key_consents={"openai": True})
        assert credential_source(consented, "openai") == "missing"
