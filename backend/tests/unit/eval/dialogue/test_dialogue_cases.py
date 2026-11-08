from copy import deepcopy

import eval.scenario_tools.scenario as scenario
import pytest
from eval.dialogue.cases import CASES, case_for_scenario_name, scenario_for


def test_two_npc_fixture_has_repeatable_identity_and_statblock():
    first = scenario_for("two_npc_two_beat")
    second = scenario_for("two_npc_two_beat")
    assert first.campaign.world_state == second.campaign.world_state


def test_cases_have_five_single_calls_and_bounded_two_beat_case():
    assert [(case.name, case.ceiling) for case in CASES] == [
        ("npc_speaks", 1),
        ("npc_followup", 1),
        ("actor_en", 1),
        ("actor_it", 1),
        ("actor_silent", 1),
        ("two_npc_two_beat", 7),
        ("npc_followup_short", 1),
        ("actor_scene", 1),
        ("two_npc_natural", 7),
        ("two_npc_conversation", 14),
    ]


def test_realistic_cases_are_separate_from_unchanged_core():
    core = scenario_for("two_npc_two_beat")
    natural = scenario_for("two_npc_natural")
    assert core.stimuli["npc_speaks"].player == (
        "Aldric and Mira, tell me independently what you each know about the old mines. "
        "Then Aldric, respond specifically to what Mira said."
    )
    assert natural.stimuli["npc_speaks"].player != core.stimuli["npc_speaks"].player
    assert case_for_scenario_name(natural.name).expected_relevance is True
    assert scenario_for("actor_scene").name == "pr2-case-actor_scene"
    assert scenario_for("npc_followup_short").stimuli["npc_followup"].npc_dialogue == "No."


@pytest.mark.parametrize(
    "name",
    [
        "npc_speaks",
        "npc_followup",
        "actor_en",
        "actor_it",
        "actor_silent",
        "two_npc_two_beat",
        "npc_followup_short",
        "actor_scene",
        "two_npc_natural",
        "two_npc_conversation",
    ],
)
def test_scenarios_preserve_capture_and_are_isolated(name):
    original = scenario.load("debug-thornhaven")
    expected_history = deepcopy(original.history)
    expected_summary = (
        original.global_summary,
        original.summary_context,
        deepcopy(original.recall),
    )

    first = scenario_for(name)
    first.campaign.world_state["meta"]["case_test_mutation"] = True
    second = scenario_for(name)

    assert second.name == f"pr2-case-{name}"
    assert second.reconstructed is True
    assert second.history == expected_history
    assert (second.global_summary, second.summary_context, second.recall) == expected_summary
    assert second.language == second.campaign.language
    assert "controlled overlay" in second.notes
    assert "npc_speaks" in second.stimuli
    assert "case_test_mutation" not in second.campaign.world_state["meta"]
    assert original.history == expected_history


def test_actor_language_cases_deliberately_conflict_with_player_input():
    english = scenario_for("actor_en")
    italian = scenario_for("actor_it")

    assert english.language == "en"
    assert "sai chi sono" in english.stimuli["npc_speaks"].player
    assert italian.language == "it"
    assert "do you know who I am" in italian.stimuli["npc_speaks"].player


def test_silent_actor_has_only_descriptive_vow_in_traits():
    sc = scenario_for("actor_silent")
    npc = next(iter(sc.campaign.world_state["npcs"].values()))

    assert "vow of silence" in npc["traits"]["personality"]
    assert "silent" not in npc
    assert "status" not in npc


def test_two_beat_overlay_has_exactly_two_present_npcs_and_uses_update_tool_shape():
    sc = scenario_for("two_npc_two_beat")
    world = sc.campaign.world_state
    location = world["meta"]["current_location"]
    present = [
        npc
        for npc in world["npcs"].values()
        if npc.get("lifecycle") == "alive" and npc.get("location") == location
    ]

    assert {npc["name"] for npc in present} == {"Aldric", "Mira"}
    mira = next(npc for npc in present if npc["name"] == "Mira")
    assert mira["traits"]["role"] == "Village courier"
    assert mira["traits"]["personality"]
    assert mira["traits"]["secret"] == ""
    assert sc.language == "it"
    assert "independently" in sc.stimuli["npc_speaks"].player
    assert "respond specifically" in sc.stimuli["npc_speaks"].player


def test_unknown_case_is_rejected():
    with pytest.raises(ValueError, match="unknown dialogue case"):
        scenario_for("not-a-case")


@pytest.mark.parametrize("name", ["two_npc_natural", "two_npc_conversation"])
def test_courier_seal_exists_only_in_the_new_natural_fixture_inventory(name):
    natural = scenario_for(name)
    inventory = natural.campaign.character_data["inventory"]
    assert any(item["name"] == "Broken courier seal" for item in inventory)
    assert "north road" in inventory[-1]["description"]
    assert scenario_for("two_npc_two_beat").campaign.character_data["inventory"] == []
    assert scenario.load("debug-thornhaven").campaign.character_data["inventory"] == []
