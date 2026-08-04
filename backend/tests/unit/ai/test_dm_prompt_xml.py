"""Unit tests for the XML-structured DM system prompt."""

from unittest.mock import MagicMock

from app.ai.prompts.dm import build_dm_system_prompt
from app.core.npc_resolver import npcs_at_current_location
from app.models.campaign import Difficulty


def _make_campaign(
    world_state: dict, character_data: dict, quests: dict | None = None
) -> MagicMock:
    c = MagicMock()
    c.world_state = world_state
    c.character_data = character_data
    c.quests = quests or {}
    c.difficulty = Difficulty.MEDIUM
    c.world_baseline = None
    return c


_WORLD_STATE = {
    "meta": {"current_location": "Thornhaven", "current_season": "autumn"},
    "time_of_day": "evening",
    "weather": "light rain",
    "clock": {"total_minutes": 3 * 24 * 60 + 17 * 60},  # day 4, 17:00
    "npcs": {
        # uuid-keyed engine records (ADR 0009 F1); names live in the record.
        "11111111-0000-0000-0000-000000000001": {
            "name": "Marta",
            "lifecycle": "alive",
            "traits": {"role": "Tavern keeper"},
            "location": "Thornhaven",
            "psychology": {"trust": 45, "fear": 80},
        },
        "11111111-0000-0000-0000-000000000002": {
            "name": "Guard",
            "lifecycle": "alive",
            "traits": {"role": "Watch"},
            "location": "Thornhaven",
            "psychology": {"trust": 5},
        },
        "11111111-0000-0000-0000-000000000003": {
            "name": "Aldric",
            "lifecycle": "alive",
            "traits": {"role": "Village elder"},
            "location": "North Road",
        },
    },
}

_CHAR_DATA = {
    "name": "Eron",
    # The production shape: apply_hp_delta writes {current, max}, never a scalar.
    "hp": {"current": 12, "max": 20},
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
    assert "```json" not in prompt
    assert '"meta":' not in prompt  # no raw JSON dump


def test_character_section_has_vitals():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert 'name="Eron"' in prompt
    assert 'hp="wounded"' in prompt
    assert 'location="Thornhaven"' in prompt


def test_character_hp_is_a_band_never_a_number():
    """0003 computes every HP number; the DM narrates from a band and never does arithmetic."""
    for hp, band in (
        ({"current": 20, "max": 20}, "unharmed"),
        ({"current": 16, "max": 20}, "grazed"),
        ({"current": 12, "max": 20}, "wounded"),
        ({"current": 6, "max": 20}, "bloodied"),
        ({"current": 1, "max": 20}, "near_death"),
    ):
        campaign = _make_campaign(_WORLD_STATE, {**_CHAR_DATA, "hp": hp})
        prompt = build_dm_system_prompt(campaign)
        assert f'hp="{band}"' in prompt
        assert f"{hp['current']}/{hp['max']}" not in prompt


def test_npcs_filtered_to_current_location():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    # Marta and Guard are at Thornhaven → should appear
    assert 'name="Marta"' in prompt
    assert 'name="Guard"' in prompt
    # Aldric is at North Road → should NOT appear
    assert 'name="Aldric"' not in prompt


def test_scene_npc_shows_salient_axes_only():
    # ADR 0005 A5: only axes outside the default band appear.
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)

    assert '<npc name="Marta" role="Tavern keeper" trust="trusting" fear="terrified"/>' in prompt


def test_scene_npc_shows_condition_and_scene_traits_only():
    # ADR 0009 A5/G3: condition + scene-flagged traits (role, appearance) reach
    # the DM; interiority traits (secret, personality, ...) never do.
    ws = {
        **_WORLD_STATE,
        "npcs": {
            "u-1": {
                "name": "Marta",
                "lifecycle": "alive",
                "condition": "wounded arm",
                "location": "Thornhaven",
                "traits": {
                    "role": "Tavern keeper",
                    "appearance": "stout, flour-dusted",
                    "secret": "poisons the ale",
                },
            },
            "u-2": {
                "name": "Guard",
                "lifecycle": "alive",
                "location": "Thornhaven",
                "psychology": {"trust": 5},
                "traits": {"role": "Watch"},
            },
        },
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    assert 'appearance="stout, flour-dusted"' in prompt
    assert 'condition="wounded arm"' in prompt
    assert "poisons the ale" not in prompt
    # Guard's trust=5 sits in the default band → clean line, no axis attrs
    assert '<npc name="Guard" role="Watch"/>' in prompt


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

    assert '<history label="story_so_far">' in prompt
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


def test_no_combat_block_when_inactive():
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA)
    prompt = build_dm_system_prompt(campaign)
    assert "<combat" not in prompt


def test_npcs_at_current_location_helper():
    result = npcs_at_current_location(_WORLD_STATE)
    names = {n["name"] for n in result.values()}
    assert names == {"Marta", "Guard"}  # Aldric is elsewhere


def test_npcs_at_current_location_empty_location_returns_all():
    ws = {**_WORLD_STATE, "meta": {}}
    result = npcs_at_current_location(ws)
    assert len(result) == 3  # fallback: all NPCs


def test_prompts_loaded_from_yaml():
    # B-M6: prompt content is externalized to dm.yaml and loaded at import.
    from app.ai.prompts.dm import BASE_DM_PROMPT

    assert BASE_DM_PROMPT.startswith("You are an expert Dungeon Master")
