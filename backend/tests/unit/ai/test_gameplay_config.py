"""Tests for gameplay and summarization configuration."""

from app.ai.router import (
    _NPC_VERBOSITY_MAP,
    GameplayConfig,
    get_gameplay_config,
)


class TestGameplayConfig:
    def test_default_values(self):
        config = GameplayConfig()
        assert config.npc_verbosity == "medium"
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


class TestGetGameplayConfig:
    def test_loads_from_yaml(self):
        config = get_gameplay_config()
        assert isinstance(config, GameplayConfig)
        assert config.auto_create_npcs is True
        assert config.npc_auto_create_detail == "standard"
        assert config.consecutive_empty_steps_max == 2

    def test_env_override_consecutive_empty_steps(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_CONSECUTIVE_EMPTY_STEPS_MAX", "3")
        config = get_gameplay_config()
        assert config.consecutive_empty_steps_max == 3

    def test_env_override_npc_auto_create_detail(self, monkeypatch):
        monkeypatch.setenv("SAGA_GAMEPLAY_NPC_AUTO_CREATE_DETAIL", "rich")
        config = get_gameplay_config()
        assert config.npc_auto_create_detail == "rich"
