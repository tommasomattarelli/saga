"""Unit tests for the XML-structured DM system prompt."""

from unittest.mock import MagicMock

from app.ai.prompts.dm import build_dm_system_prompt
from app.core.npc_resolver import npcs_at_current_location
from app.memory.graph_config import GraphConfig
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


def test_scene_relation_carries_reason_and_game_time_only():
    npc_id = "11111111-0000-0000-0000-000000000003"  # Aldric, away from the scene
    ws = {
        **_WORLD_STATE,
        "relations": [
            {
                "src": {"type": "npc", "id": npc_id},
                "dst": {"type": "player", "id": None},
                "kind": "companion",
                "stance": 60,
                "label": "Travels with you",
                "prominent": True,
                "since_turn": 18,
                "since_game_minutes": (3 * 24 + 17) * 60 - (3 * 1440 + 4 * 60),
            }
        ],
    }
    campaign = _make_campaign(ws, _CHAR_DATA)
    campaign.language = "it"
    prompt = build_dm_system_prompt(campaign)

    assert (
        '<relation from="Aldric" to="player" kind="companion" stance="60" '
        'since="3d4h" ago="3 days, 4 hours" why="Travels with you"/>' in prompt
    )
    assert "18 turni" not in prompt
    assert "18 turns" not in prompt
    assert "18t/" not in prompt


def test_scene_faction_relations_keep_bands_and_name_factions():
    ws = {
        **_WORLD_STATE,
        "factions": {
            "guild": {"name": "Merchants Guild", "description": "Traders of the town"},
            "council": {"name": "Council", "description": "Village elders"},
        },
        "relations": [
            {
                "src": {"type": "faction", "id": "guild"},
                "dst": {"type": "faction", "id": "council"},
                "kind": "faction",
                "stance": -70,
                "label": "fearful hostility",
                "prominent": False,
            },
            {
                "src": {"type": "faction", "id": "guild"},
                "dst": {"type": "faction", "id": "council"},
                "kind": "faction",
                "stance": 0,
                "label": "indifferent",
                "prominent": False,
            },
            {
                "src": {"type": "faction", "id": "guild"},
                "dst": {"type": "player", "id": None},
                "kind": "reputation",
                "stance": 0,
                "label": "neutral",
                "prominent": True,
            },
            {
                "src": {"type": "faction", "id": "council"},
                "dst": {"type": "player", "id": None},
                "kind": "reputation",
                "stance": 40,
                "label": "trusted",
                "prominent": True,
            },
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    relations_block = prompt.split("<relations", 1)[1].split("</relations>", 1)[0]
    factions_block = prompt.split("<factions", 1)[1].split("</factions>", 1)[0]

    assert 'from="Merchants Guild" to="Council"' in factions_block
    assert 'why="fearful hostility"' in factions_block
    assert 'why="neutral"' in factions_block  # reputation band survives a zero stance
    assert 'why="trusted"' in factions_block
    assert "indifferent" not in factions_block
    assert "Merchants Guild" not in relations_block
    assert (
        "<factions_known>Merchants Guild: Traders of the town | "
        "Council: Village elders</factions_known>" in prompt
    )


def test_scene_reputation_band_leads_faction_cap():
    hostiles = [
        {
            "src": {"type": "faction", "id": "guild"},
            "dst": {"type": "faction", "id": "council"},
            "kind": "faction",
            "stance": -10 * (index + 1),
            "label": f"feud {index}",
            "prominent": False,
        }
        for index in range(9)
    ]
    ws = {
        **_WORLD_STATE,
        "factions": {"guild": {"name": "Guild"}, "council": {"name": "Council"}},
        "relations": hostiles
        + [
            {
                "src": {"type": "faction", "id": "guild"},
                "dst": {"type": "player", "id": None},
                "kind": "reputation",
                "stance": 0,
                "label": "neutral",
                "prominent": True,
            }
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    factions_block = prompt.split("<factions ", 1)[1].split("</factions>", 1)[0]

    assert 'why="neutral"' in factions_block
    assert '<factions shown="8" omitted="2">' in prompt


def test_scene_npc_faction_edges_follow_scene_presence():
    present_id = "11111111-0000-0000-0000-000000000001"  # Marta
    away_id = "11111111-0000-0000-0000-000000000003"  # Aldric
    ws = {
        **_WORLD_STATE,
        "factions": {"guild": {"name": "Merchants Guild"}},
        "relations": [
            {
                "src": {"type": "npc", "id": present_id},
                "dst": {"type": "faction", "id": "guild"},
                "kind": "ally",
                "stance": 30,
                "label": "trades fairly",
                "prominent": False,
            },
            {
                "src": {"type": "npc", "id": away_id},
                "dst": {"type": "faction", "id": "guild"},
                "kind": "ally",
                "stance": 30,
                "label": "former member",
                "prominent": False,
            },
            {
                "src": {"type": "npc", "id": away_id},
                "dst": {"type": "faction", "id": "guild"},
                "kind": "nemesis",
                "stance": -90,
                "label": "hunted by the guild",
                "prominent": True,
            },
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    relations_block = prompt.split("<relations", 1)[1].split("</relations>", 1)[0]
    present_block = prompt.split("<npcs_present", 1)[1].split("</npcs_present>", 1)[0]

    assert 'why="trades fairly"' in present_block
    assert "former member" not in prompt
    assert 'why="hunted by the guild"' in relations_block
    assert "<factions " not in prompt


def test_scene_relation_omits_unknown_clock():
    ws = {
        **_WORLD_STATE,
        "clock": {"total_minutes": 600},
        "relations": [
            {
                "src": {"type": "npc", "id": "11111111-0000-0000-0000-000000000003"},
                "dst": {"type": "player", "id": None},
                "kind": "ally",
                "stance": 20,
                "label": "old debt",
                "prominent": True,
            }
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    assert 'why="old debt"' in prompt
    assert "since=" not in prompt
    assert "ago=" not in prompt


def test_scene_relation_blocks_rank_by_stance_and_report_omitted(monkeypatch):
    monkeypatch.setattr(
        "app.ai.prompts.dm.get_graph_config",
        lambda: GraphConfig(
            max_relations=50,
            prominent_max_relations=1,
            scene_max_relations=1,
            faction_max_relations=1,
            extract_max_per_batch=8,
        ),
    )
    present_id = "11111111-0000-0000-0000-000000000001"  # Marta
    guard_id = "11111111-0000-0000-0000-000000000002"  # Guard
    away_id = "11111111-0000-0000-0000-000000000003"  # Aldric
    ws = {
        **_WORLD_STATE,
        "factions": {
            "guild": {"name": "Merchants Guild"},
            "council": {"name": "Council"},
        },
        "relations": [
            {
                "src": {"type": "npc", "id": away_id},
                "dst": {"type": "player", "id": None},
                "kind": "ally",
                "stance": 20,
                "label": "weak ally",
                "prominent": True,
            },
            {
                "src": {"type": "npc", "id": guard_id},
                "dst": {"type": "player", "id": None},
                "kind": "nemesis",
                "stance": 80,
                "label": "sworn foe",
                "prominent": True,
            },
            {
                "src": {"type": "faction", "id": "guild"},
                "dst": {"type": "faction", "id": "council"},
                "kind": "faction",
                "stance": -10,
                "label": "mild distrust",
                "prominent": False,
            },
            {
                "src": {"type": "faction", "id": "council"},
                "dst": {"type": "faction", "id": "guild"},
                "kind": "faction",
                "stance": -80,
                "label": "open war",
                "prominent": False,
            },
            {
                "src": {"type": "npc", "id": present_id},
                "dst": {"type": "player", "id": None},
                "kind": "ally",
                "stance": 5,
                "label": "polite",
                "prominent": False,
            },
            {
                "src": {"type": "npc", "id": guard_id},
                "dst": {"type": "player", "id": None},
                "kind": "ally",
                "stance": 50,
                "label": "helps in a fight",
                "prominent": False,
            },
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    relations_block = prompt.split("<relations", 1)[1].split("</relations>", 1)[0]
    factions_block = prompt.split("<factions", 1)[1].split("</factions>", 1)[0]
    present_block = prompt.split("<npcs_present", 1)[1].split("</npcs_present>", 1)[0]

    assert '<relations shown="1" omitted="1">' in prompt
    assert 'stance="80"' in relations_block and "weak ally" not in relations_block
    assert '<factions shown="1" omitted="1">' in prompt
    assert 'stance="-80"' in factions_block and "mild distrust" not in factions_block
    assert 'relations_omitted="1"' in prompt
    assert 'stance="50"' in present_block and "polite" not in present_block


def test_scene_relation_escapes_quoted_endpoint_names():
    ws = {
        "meta": {"current_location": "Thornhaven"},
        "npcs": {
            "q1": {
                "name": 'The "Grey" One',
                "lifecycle": "alive",
                "location": "Thornhaven",
            }
        },
        "relations": [
            {
                "src": {"type": "npc", "id": "q1"},
                "dst": {"type": "player", "id": None},
                "kind": "ally",
                "stance": 10,
                "prominent": True,
                "since_turn": 1,
                "since_game_minutes": 480,
            }
        ],
    }
    prompt = build_dm_system_prompt(_make_campaign(ws, _CHAR_DATA))
    assert "from='The \"Grey\" One'" in prompt or 'from="The &quot;Grey&quot; One"' in prompt


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


def test_quests_section_renders_active_ids_and_descriptions_only():
    quests = {
        "active": [
            {
                "id": "who_am_i",
                "name": "Who Am I?",
                "description": "Discover your identity.",
                "objectives": ["Ask the villagers"],
            }
        ],
        "completed": [
            {
                "id": "old_deed",
                "name": "Old Deed",
                "description": "Already done.",
                "objectives": [],
            }
        ],
        "failed": [],
        "abandoned": [],
    }
    campaign = _make_campaign(_WORLD_STATE, _CHAR_DATA, quests=quests)
    prompt = build_dm_system_prompt(campaign)

    assert "<quests>" in prompt
    assert '<quest id="who_am_i">Discover your identity.</quest>' in prompt
    assert "Who Am I?" not in prompt
    assert "Ask the villagers" not in prompt
    assert "old_deed" not in prompt
    assert "Already done." not in prompt


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
