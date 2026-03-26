"""Tests for gameplay configuration and NPC verbosity mapping."""

from app.ai.router import _NPC_VERBOSITY_MAP, GameplayConfig


class TestGameplayConfig:
    def test_default_values(self):
        config = GameplayConfig()
        assert config.context_window_turns == 8
        assert config.npc_verbosity == "medium"
        assert config.compression_enabled is True
        assert config.fact_extraction_enabled is True

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
