"""Tests for gameplay and summarization configuration."""

import pytest

from app.ai.router import (
    GameplayConfig,
    SummarizationConfig,
    _NPC_VERBOSITY_MAP,
    get_gameplay_config,
    get_summarization_config,
)


class TestGameplayConfig:
    def test_default_values(self):
        config = GameplayConfig()
        assert config.context_window_turns == 8
        assert config.context_token_cap == 12000
        assert config.npc_verbosity == "medium"
        assert config.compression_enabled is True
        assert config.fact_extraction_enabled is True
        assert config.global_summary_enabled is True
        assert config.global_summary_update_every == 5
        assert config.pgvector_hybrid is False
        assert config.auto_create_npcs is True
        assert config.npc_auto_create_detail == "standard"
        assert config.consecutive_empty_steps_max == 2

    def test_max_npc_calls_mapping(self):
        assert GameplayConfig(npc_verbosity="null").max_npc_calls == 0
        assert GameplayConfig(npc_verbosity="minimal").max_npc_calls == 1
        assert GameplayConfig(npc_verbosity="low").max_npc_calls == 2
        assert GameplayConfig(npc_verbosity="medium").max_npc_calls == 3
        assert GameplayConfig(npc_verbosity="high").max_npc_calls == 5
        assert GameplayConfig(npc_verbosity="unlimited").max_npc_calls == 999

    def test_unknown_verbosity_defaults_to_3(self):
        assert GameplayConfig(npc_verbosity="bogus").max_npc_calls == 3

    def test_verbosity_map_complete(self):
        expected_keys = {"null", "minimal", "low", "medium", "high", "unlimited"}
        assert set(_NPC_VERBOSITY_MAP.keys()) == expected_keys


class TestSummarizationConfig:
    def test_default_values(self):
        config = SummarizationConfig()
        assert config.max_retries == 3
        assert config.retry_delays_seconds == [1, 5, 30]

    def test_custom_values(self):
        config = SummarizationConfig(max_retries=5, retry_delays_seconds=[2, 10])
        assert config.max_retries == 5
        assert config.retry_delays_seconds == [2, 10]

    def test_retry_delays_default_when_none(self):
        config = SummarizationConfig(retry_delays_seconds=None)
        assert config.retry_delays_seconds == [1, 5, 30]


class TestGetGameplayConfig:
    def test_loads_from_yaml(self):
        config = get_gameplay_config()
        assert isinstance(config, GameplayConfig)
        assert config.context_window_turns == 8
        assert config.context_token_cap == 12000
        assert config.global_summary_enabled is True
        assert config.global_summary_update_every == 5
        assert config.pgvector_hybrid is False
        assert config.auto_create_npcs is True
        assert config.npc_auto_create_detail == "standard"
        assert config.consecutive_empty_steps_max == 2

    def test_env_override_context_token_cap(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_CONTEXT_TOKEN_CAP", "8000")
        from app.config_loader import load_saga_config
        load_saga_config.cache_clear()
        config = get_gameplay_config()
        assert config.context_token_cap == 8000

    def test_env_override_pgvector_hybrid(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_PGVECTOR_HYBRID", "true")
        config = get_gameplay_config()
        assert config.pgvector_hybrid is True

    def test_env_override_global_summary_disabled(self, monkeypatch):
        monkeypatch.setenv("SAGA_GLOBAL_SUMMARY_ENABLED", "false")
        config = get_gameplay_config()
        assert config.global_summary_enabled is False

    def test_env_override_global_summary_interval(self, monkeypatch):
        monkeypatch.setenv("SAGA_GLOBAL_SUMMARY_INTERVAL_TURNS", "10")
        config = get_gameplay_config()
        assert config.global_summary_update_every == 10

    def test_env_override_consecutive_empty_steps(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_CONSECUTIVE_EMPTY_STEPS_MAX", "3")
        config = get_gameplay_config()
        assert config.consecutive_empty_steps_max == 3

    def test_env_override_npc_auto_create_detail(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_NPC_AUTO_CREATE_DETAIL", "rich")
        config = get_gameplay_config()
        assert config.npc_auto_create_detail == "rich"


class TestGetSummarizationConfig:
    def test_loads_from_yaml(self):
        config = get_summarization_config()
        assert isinstance(config, SummarizationConfig)
        assert config.max_retries == 3
        assert config.retry_delays_seconds == [1, 5, 30]

    def test_env_override_max_retries(self, monkeypatch):
        monkeypatch.setenv("SAGA_SUMMARIZATION_MAX_RETRIES", "5")
        config = get_summarization_config()
        assert config.max_retries == 5
