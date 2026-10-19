"""Tests for embedding profile/credential resolution (ADR 0018 B1, A3/A4)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from app.ai.credentials import resolve_embedding, resolve_generation
from app.ai.embedding_config import (
    NEW_PIPELINE,
    EmbeddingSpace,
    build_space,
    check_space_contract,
    get_embedding_default_space,
    get_embedding_policy,
    legacy_space,
    local_space,
)
from app.config import settings
from app.exceptions import ValidationError
from app.security.encryption import encrypt_api_key


def _user(**overrides) -> Mock:
    user = Mock()
    user.generation_provider = None
    user.generation_model = None
    user.generation_local_endpoint = None
    user.embedding_provider = None
    user.embedding_model = None
    user.embedding_local_endpoint = None
    user.openai_api_key_enc = None
    user.openrouter_api_key_enc = None
    user.google_api_key_enc = None
    user.server_key_consents = None
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


class TestUserDefaults:
    def test_no_profile_inherits_the_openrouter_instance_default(self):
        with pytest.raises(ValidationError, match="key"):
            resolve_embedding(_user())

    def test_default_space_identity_comes_from_yaml(self):
        space = get_embedding_default_space()
        assert isinstance(space, EmbeddingSpace)
        assert space.provider == "openrouter"
        assert space.model == "openai/text-embedding-3-small"
        assert space.requested_dimensions is None
        check_space_contract(space)


class TestPersonalProfile:
    def test_valid_personal_profile_resolves_space_and_plaintext_key(self):
        user = _user(
            openrouter_api_key_enc=encrypt_api_key("personal-or-key"),
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        resolved = resolve_embedding(user)
        assert resolved.space.provider == "openrouter"
        assert resolved.space.model == "openai/mistral-embed"
        assert resolved.space.pipeline_version == "embed-v1"
        assert resolved.space.requested_dimensions is None
        assert resolved.credential.key == "personal-or-key"
        assert resolved.credential.source == "personal"
        assert resolved.policy.batch_size == 32

    def test_partial_profile_is_rejected(self):
        with pytest.raises(ValidationError, match="provider and.*model"):
            resolve_embedding(_user(embedding_provider="openrouter"))

    def test_openrouter_profile_never_takes_the_openai_server_key(self):
        user = _user(
            server_key_consents={"openrouter": True},
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with (
            patch.object(settings, "openrouter_api_key", "server-or-key"),
            patch.object(settings, "openai_api_key", "server-openai-key"),
            patch("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True}),
        ):
            resolved = resolve_embedding(user)
        assert resolved.credential.key == "server-or-key"
        assert resolved.credential.source == "server"

    def test_disabled_provider_is_rejected_at_resolution(self):
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["google"]),
            pytest.raises(ValidationError, match="not enabled"),
        ):
            resolve_embedding(
                _user(embedding_provider="openrouter", embedding_model="openai/mistral-embed")
            )

    def test_space_identity_carries_no_credential_material(self):
        user = _user(
            openrouter_api_key_enc=encrypt_api_key("personal-or-key"),
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        space = resolve_embedding(user).space
        observed = [key for key in vars(space) if "key" in key.lower()]
        assert observed == []

    def test_direct_openai_small_is_a_native_new_space(self):
        user = _user(
            openai_api_key_enc=encrypt_api_key("personal-openai"),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )
        space = resolve_embedding(user).space
        assert space.pipeline_version == NEW_PIPELINE
        assert space.requested_dimensions is None


class TestServerFallback:
    @pytest.fixture(autouse=True)
    def operator_keys(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "openrouter_api_key", "server-or-key")
        monkeypatch.setattr(settings, "google_ai_api_key", "server-google-key")

    def test_fallback_needs_operator_and_user_consent(self):
        user = _user(
            server_key_consents={"openrouter": True},
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with patch("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True}):
            resolved = resolve_embedding(user)
        assert resolved.credential.source == "server"

    def test_personal_key_wins_before_any_consented_fallback(self):
        user = _user(
            openrouter_api_key_enc=encrypt_api_key("personal-or-key"),
            server_key_consents={"openrouter": True},
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with patch("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True}):
            resolved = resolve_embedding(user)
        assert resolved.credential.key == "personal-or-key"
        assert resolved.credential.source == "personal"

    def test_unreadable_personal_key_never_falls_back_to_the_server_key(self):
        user = _user(
            openrouter_api_key_enc="broken-ciphertext",
            server_key_consents={"openrouter": True},
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with (
            patch("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": True}),
            pytest.raises(ValidationError, match="personal key"),
        ):
            resolve_embedding(user)

    def test_missing_aggregation_never_silently_switches_providers(self):
        user = _user(
            server_key_consents={"openrouter": True},
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with (
            patch("app.ai.credentials.get_server_key_fallback", lambda: {"openrouter": False}),
            pytest.raises(ValidationError),
        ):
            resolve_embedding(user)


class TestGoogleProfile:
    def test_google_profile_maps_to_its_own_server_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "google_ai_api_key", "server-google-key")
        user = _user(
            server_key_consents={"google": True},
            embedding_provider="google",
            embedding_model="gemini-embedding-001",
        )
        with patch("app.ai.credentials.get_server_key_fallback", lambda: {"google": True}):
            resolved = resolve_embedding(user)
        assert resolved.space.api_family == "google"
        assert resolved.space.endpoint_identity is None
        assert resolved.space.requested_dimensions is None
        assert resolved.credential.key == "server-google-key"


class TestLocalProfile:
    def test_local_profile_resolves_today_endpoint_url(self):
        user = _user(
            embedding_provider="local",
            embedding_model="nomic-embed-text",
            embedding_local_endpoint="ollama",
        )
        resolved = resolve_embedding(user)
        assert resolved.space.endpoint_name == "ollama"
        assert resolved.space.endpoint_identity == "http://localhost:11434/v1"
        assert resolved.credential.source == "not_required"
        assert resolved.credential.key is None


class TestStoredSpaceManifest:
    """Lead guarantee 1: a fixed index space is honored verbatim, policy revalidated."""

    def test_legacy_query_space_survives_with_384(self):
        user = _user(
            openai_api_key_enc=encrypt_api_key("personal-openai"),
        )
        resolved = resolve_embedding(user, legacy_space())
        assert resolved.space.requested_dimensions == 384
        assert resolved.space.pipeline_version == "embed-v1-legacy"
        assert resolved.credential.key == "personal-openai"

    def test_legacy_space_never_substitutes_the_personal_profile(self):
        user = _user(
            openai_api_key_enc=encrypt_api_key("personal-openai"),
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        space = legacy_space()
        resolved = resolve_embedding(user, space)
        assert resolved.space is space
        assert resolved.space.provider == "openai"
        assert resolved.space.requested_dimensions == 384

    def test_legacy_space_without_an_authorized_credential_fails(self):
        with pytest.raises(ValidationError, match="openai"):
            resolve_embedding(_user(), legacy_space())

    def test_stored_local_alias_url_snapshot_is_never_reused(self):
        user = _user(
            embedding_provider="local",
            embedding_model="nomic-embed-text",
            embedding_local_endpoint="ollama",
        )
        stored = local_space("ollama", "nomic-embed-text")
        moved = replace(stored, endpoint_identity="http://10.9.9.9:11434/v1")
        with pytest.raises(ValidationError, match="no longer authorized"):
            resolve_embedding(user, moved)

    def test_removed_local_alias_is_rejected_today(self):
        user = _user()
        stored = local_space("ollama", "nomic-embed-text")
        with (
            patch(
                "app.ai.embedding_config.get_local_endpoints",
                lambda: {"other": "http://localhost:11435/v1"},
            ),
            pytest.raises(ValidationError, match="not authorized on this instance"),
        ):
            resolve_embedding(user, stored)

    def test_disabled_provider_manifest_fails_today(self):
        stored = build_space("openrouter", "openai/text-embedding-3-small")
        user = _user(
            openrouter_api_key_enc=encrypt_api_key("personal-or-key"),
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        with (
            patch("app.ai.embedding_config.get_allowed_providers", lambda: ["google"]),
            pytest.raises(ValidationError, match="not enabled"),
        ):
            resolve_embedding(user, stored)

    def test_manifest_with_the_wrong_transport_is_rejected_before_credentials(self):
        stored = replace(build_space("openai", "text-embedding-3-small"), api_family="google")
        user = _user()  # no key at all: credential resolution must never be reached
        with pytest.raises(ValidationError, match="transport"):
            resolve_embedding(user, stored)


class TestGenerationCompatibility:
    def test_generation_profile_is_independent_of_the_embedding_profile(self):
        user = _user(
            generation_provider="local",
            generation_model="local-model",
            generation_local_endpoint="ollama",
            openrouter_api_key_enc=encrypt_api_key("personal-or-key"),
            embedding_provider="openrouter",
            embedding_model="openai/mistral-embed",
        )
        generation = resolve_generation(user)
        embedding = resolve_embedding(user)
        assert generation[0].provider == "local"
        assert generation[1] is None
        assert embedding.space.provider == "openrouter"
        assert embedding.policy.batch_size == 32

    def test_policy_travelers_match_the_owner_decision(self):
        policy = get_embedding_policy()
        assert policy.rebuild_min_interval_seconds >= 1
        assert policy.rebuild_concurrency == 1
        assert policy.max_retries == 2
        assert policy.retry_delays_seconds == (1, 3)
        assert policy.request_timeout_seconds == 30
