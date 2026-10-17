"""Tests for the ADR 0018 generation configuration."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ai.router import (
    get_allowed_providers,
    get_instance_default,
    get_local_endpoints,
    get_server_key_fallback,
    validate_generation_config,
)
from app.config_loader import load_saga_config


class TestGenerationBlock:
    def test_tiered_routing_sections_are_gone(self):
        config = load_saga_config()
        for gone in (
            "dm_narration",
            "companion_dialogue",
            "npc_behavior",
            "world_sim",
            "memory_compression",
        ):
            assert gone not in config

    def test_instance_default_reads_the_generation_block(self):
        config = get_instance_default()
        assert config.provider == "google"
        assert config.model == "gemini-3.5-flash"
        assert config.max_tokens == 60000

    def test_missing_cap_fails_fast(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={"generation": {"default": {"provider": "google", "model": "x"}}},
            ),
            pytest.raises(ValueError, match="max_output_tokens"),
        ):
            get_instance_default()


class TestProviderPolicy:
    def test_allowed_providers_from_yaml(self):
        assert get_allowed_providers() == ["openai", "openrouter", "google", "local"]

    def test_allow_all_expands_to_supported_providers(self):
        with patch(
            "app.ai.router._load_config",
            return_value={"providers": {"allowed": "all"}},
        ):
            assert get_allowed_providers() == ["openai", "openrouter", "google", "local"]

    def test_server_key_fallback_defaults_off(self):
        assert get_server_key_fallback() == {
            "openai": False,
            "openrouter": False,
            "google": False,
        }

    def test_local_endpoints_are_named_and_http(self):
        endpoints = get_local_endpoints()
        assert "ollama" in endpoints
        assert endpoints["ollama"].startswith(("http://", "https://"))


class TestValidateGenerationConfig:
    def test_unconfigured_default_local_endpoint_is_rejected(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={
                    "generation": {
                        "default": {"provider": "local", "model": "local-model"},
                        "max_output_tokens": 60000,
                    },
                    "providers": {"allowed": ["local"], "local_endpoints": {}},
                },
            ),
            pytest.raises(ValueError, match="local_endpoint"),
        ):
            validate_generation_config()

    def test_repo_config_is_valid(self):
        validate_generation_config()

    def test_unknown_default_provider_is_rejected(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={
                    "generation": {
                        "default": {"provider": "not-a-provider", "model": "m"},
                        "max_output_tokens": 60000,
                    },
                    "providers": {"allowed": ["google"]},
                },
            ),
            pytest.raises(ValueError, match="not in providers.allowed"),
        ):
            validate_generation_config()

    def test_empty_model_is_rejected(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={
                    "generation": {
                        "default": {"provider": "google", "model": ""},
                        "max_output_tokens": 60000,
                    },
                    "providers": {"allowed": ["google"]},
                },
            ),
            pytest.raises(ValueError, match="model is empty"),
        ):
            validate_generation_config()

    def test_non_positive_cap_is_rejected(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={
                    "generation": {
                        "default": {"provider": "google", "model": "m"},
                        "max_output_tokens": 0,
                    },
                    "providers": {"allowed": ["google"]},
                },
            ),
            pytest.raises(ValueError, match="positive integer"),
        ):
            validate_generation_config()

    def test_bad_local_endpoint_is_rejected(self):
        with (
            patch(
                "app.ai.router._load_config",
                return_value={
                    "generation": {
                        "default": {"provider": "local", "model": "m"},
                        "max_output_tokens": 60000,
                    },
                    "providers": {
                        "allowed": ["local"],
                        "local_endpoints": {"bad": {"base_url": "not-a-url"}},
                    },
                },
            ),
            pytest.raises(ValueError, match="http"),
        ):
            validate_generation_config()
