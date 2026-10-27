from types import SimpleNamespace

import scenario as scenarios
from capture_scenario import assemble


def test_captured_scenario_reports_probes_it_cannot_ask() -> None:
    sc = scenarios.load("debug-shrine")

    assert sc.reconstructed is False
    assert "npc_speaks" in sc.unsupported
    assert "npc_followup" in sc.unsupported
    assert "travel_move" in sc.stimuli
    assert sc.campaign.world_baseline["nodes"]


def test_reconstructed_scenario_is_labelled_and_moves_the_player() -> None:
    sc = scenarios.load("debug-thornhaven")

    assert sc.reconstructed is True
    assert (
        sc.campaign.world_state["player_position"]
        == sc.campaign.world_state["meta"]["current_location"]
    )
    assert "npc_speaks" not in sc.unsupported


def test_overlay_inherits_the_captured_state_and_moves_only_its_language() -> None:
    base = scenarios.load("debug-thornhaven")
    overlay = scenarios.load("debug-thornhaven-it")

    assert overlay.name == "debug-thornhaven-it"
    assert overlay.language == "it"
    assert overlay.campaign.world_state == base.campaign.world_state
    assert overlay.stimuli["npc_speaks"].player != base.stimuli["npc_speaks"].player
    # Untouched probes still inherit the base stimulus.
    assert (
        overlay.stimuli["npc_followup"].npc_dialogue == base.stimuli["npc_followup"].npc_dialogue
    )


def test_empty_scenario_builds_a_prompt_with_the_current_hp_shape() -> None:
    from app.ai.prompts.dm import build_dm_system_prompt

    sc = scenarios.load("empty")
    prompt = build_dm_system_prompt(sc.campaign)  # type: ignore[arg-type]

    assert 'hp="unharmed"' in prompt


def test_assemble_marks_a_position_patch_as_reconstructed() -> None:
    campaign = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        world_state={"meta": {"current_location": "a"}, "player_position": "a"},
        world_baseline={"nodes": {}},
        character_data={},
        quests={},
        difficulty="medium",
        global_summary="",
    )
    turn = SimpleNamespace(player_action="go", narration="You go.")

    captured = assemble(
        name="x",
        campaign=campaign,
        turns=[turn],
        summary_context="",
        stimuli={"probes": {"travel_move": {"player": "go"}}},
        language="en",
        window=8,
    )
    moved = assemble(
        name="x",
        campaign=campaign,
        turns=[turn],
        summary_context="",
        stimuli={"probes": {"travel_move": {"player": "go"}}},
        language="en",
        window=8,
        position="b",
    )

    assert captured["meta"]["reconstructed"] is False
    assert moved["meta"]["reconstructed"] is True
    assert moved["campaign"]["world_state"]["player_position"] == "b"
    assert moved["campaign"]["world_state"]["meta"]["current_location"] == "b"
    assert moved["history"] == [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "You go."},
    ]
