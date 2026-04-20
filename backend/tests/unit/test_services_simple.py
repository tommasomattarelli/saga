"""Unit tests for simple services: analytics, character, export."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.character_service import CLASS_PRESETS, BASE_HP, create_default_character
from app.services.export_service import format_campaign_export
from app.services.analytics_service import track_event


class TestCreateDefaultCharacter:
    def test_returns_dict_with_required_keys(self):
        char = create_default_character("Aldric")
        for key in ("name", "level", "xp", "hp", "ac", "abilities", "skills", "inventory", "gold"):
            assert key in char

    def test_name_is_set(self):
        char = create_default_character("Zariah")
        assert char["name"] == "Zariah"

    def test_default_archetype_is_warrior(self):
        char = create_default_character("Hero")
        assert char["archetype"] == "warrior"

    def test_custom_archetype(self):
        char = create_default_character("Shadow", archetype="rogue")
        assert char["archetype"] == "rogue"
        assert char["abilities"]["dexterity"] == 16

    def test_unknown_archetype_defaults_to_warrior(self):
        char = create_default_character("Hero", archetype="unknown_class")
        warrior_abilities = CLASS_PRESETS["warrior"]
        assert char["abilities"] == warrior_abilities

    def test_hp_is_nested_dict(self):
        char = create_default_character("Test")
        assert isinstance(char["hp"], dict)
        assert char["hp"]["current"] == char["hp"]["max"]

    def test_hp_uses_constitution_modifier(self):
        char = create_default_character("Warrior", archetype="warrior")
        con = CLASS_PRESETS["warrior"]["constitution"]
        con_mod = (con - 10) // 2
        expected_hp = BASE_HP + con_mod
        assert char["hp"]["max"] == expected_hp

    def test_level_starts_at_1(self):
        char = create_default_character("New")
        assert char["level"] == 1
        assert char["xp"] == 0

    def test_all_presets_are_valid(self):
        for archetype in CLASS_PRESETS:
            char = create_default_character("Test", archetype=archetype)
            assert char["archetype"] == archetype

    def test_background_set(self):
        char = create_default_character("Bard", background="musician")
        assert char["background"] == "musician"


class TestFormatCampaignExport:
    def test_returns_expected_structure(self):
        campaign_data = {"id": "123", "name": "My Campaign"}
        turns_data = [{"turn": 1, "action": "look"}]
        result = format_campaign_export(campaign_data, turns_data)
        assert result["version"] == "1.0"
        assert result["format"] == "saga-export"
        assert result["campaign"] is campaign_data
        assert result["turns"] is turns_data

    def test_works_with_empty_turns(self):
        result = format_campaign_export({}, [])
        assert result["turns"] == []


class TestTrackEvent:
    @pytest.mark.asyncio
    async def test_no_op_when_telemetry_disabled(self):
        with patch("app.services.analytics_service.settings") as mock_settings:
            mock_settings.telemetry_enabled = False
            # Should not raise
            await track_event("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_logs_event_when_telemetry_enabled(self):
        with patch("app.services.analytics_service.settings") as mock_settings:
            mock_settings.telemetry_enabled = True
            with patch("app.services.analytics_service.logger") as mock_logger:
                await track_event("game_started", {"campaign": "test"})
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                assert call_args[0][0] == "analytics_event"

    @pytest.mark.asyncio
    async def test_handles_none_properties(self):
        with patch("app.services.analytics_service.settings") as mock_settings:
            mock_settings.telemetry_enabled = True
            with patch("app.services.analytics_service.logger") as mock_logger:
                await track_event("event_no_props")
                mock_logger.info.assert_called_once()
