"""Unit tests for the XML-structured DM system prompt."""

from unittest.mock import MagicMock

import pytest

from app.ai.prompts.dm import _npcs_at_current_location, build_dm_system_prompt
from app.models.campaign import DeathMode


def _make_campaign(world_state: dict, character_data: dict, quests: dict | None = None) -> MagicMock:
    c = MagicMock()
    c.world_state = world_state
    c.character_data = character_data
    c.quests = quests or {}
    c.death_mode = DeathMode.DESTINO
    return c


_WORLD_STATE = {
    "meta": {"current_location": "Thornhaven", "current_season": "autumn"},
    "time_of_day": "evening",
    "weather": "light rain",
    "clock": {"total_minutes": 3 * 24 * 60 + 17 * 60},  # day 4, 17:00
    "locations": {
        "Thornhaven": {
            "description": "A small village of timber-and-stone buildings.",
            "connections": ["Shrine of First Light", "Forest Path", "North Road"],
        }
    },
    "npcs": {
        "Marta": {"role": "Tavern keeper", "location": "Thornhaven", "disposition": 0},
        "Guard": {"role": "Watch", "location": "Thornhaven", "disposition": 0},
        "Aldric": {"role": "Village elder", "location": "North Road", "disposition": 5},
    },
    "combat_state": {"active": False, "round": 0, "initiative_order": []},
}

_CHAR_DATA = {
    "name": "Eron",
    "hp": 12,
    "max_hp": 20,
    "str": 16,
    "dex": 12,
    "con": 14,
    "inventory": ["Sword", "Health Potion x2"],
}


def test_xml_structure_has_required_tags():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert "<instructions>" in prompt
    assert "</instructions>" in prompt
    assert "<character" in prompt
    assert "</character>" in prompt
    assert "<scene>" in prompt
    assert "</scene>" in prompt


def test_no_json_dumps_in_prompt():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert "json.dumps" not in prompt
    assert '```json' not in prompt
    assert '"meta":' not in prompt  # no raw JSON dump


def test_character_section_has_vitals():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert 'name="Eron"' in prompt
    assert 'hp="12/20"' in prompt
    assert 'location="Thornhaven"' in prompt


def test_location_section_has_description_and_connections():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert "timber-and-stone" in prompt
    assert "Forest Path" in prompt
    assert "Connected to:" in prompt


def test_npcs_filtered_to_current_location():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    # Marta and Guard are at Thornhaven → should appear
    assert 'name="Marta"' in prompt
    assert 'name="Guard"' in prompt
    # Aldric is at North Road → should NOT appear
    assert 'name="Aldric"' not in prompt


def test_time_and_weather_in_scene():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert "<time>" in prompt
    assert "evening" in prompt
    assert "<weather>" in prompt
    assert "light rain" in prompt


def test_history_section_when_summary_present():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign, summary_context="The hero woke at the shrine.")

    assert "<history>" in prompt
    assert "The hero woke at the shrine." in prompt


def test_no_history_section_when_empty():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign, summary_context="")

    assert "<history>" not in prompt


def test_quests_section():
    quests = {"active": [{"name": "Who Am I?", "description": "Discover your identity."}]}
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA, quests=quests)
    prompt = build_dm_system_prompt(campaign)

    assert "<quests>" in prompt
    assert 'name="Who Am I?"' in prompt


def test_combat_block_only_when_active():
    ws_combat = {**_WORLD_STATE, "combat_state": {"active": True, "round": 2, "initiative_order": ["Eron", "Goblin"]}}
    campaign = _make_campaign(ws_combat, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert '<combat active="true"' in prompt
    assert "Eron" in prompt
    assert "Goblin" in prompt


def test_no_combat_block_when_inactive():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)
    assert "<combat" not in prompt


def test_npcs_at_current_location_helper():
    result = _npcs_at_current_location(_WORLD_STATE)
    assert "Marta" in result
    assert "Guard" in result
    assert "Aldric" not in result  # different location


def test_npcs_at_current_location_empty_location_returns_all():
    ws = {**_WORLD_STATE, "meta": {}}
    result = _npcs_at_current_location(ws)
    assert len(result) == 3  # fallback: all NPCs
