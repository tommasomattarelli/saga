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


def test_coherent_and_conflict_travel_cases_preserve_the_same_mechanical_inputs() -> None:
    captured = scenarios.load("debug-shrine")
    coherent = scenarios.load("travel-coherent")
    conflict = scenarios.load("travel-conflict")

    assert coherent.name == "travel-coherent" and conflict.name == "travel-conflict"
    for case in (coherent, conflict):
        assert vars(case.campaign) == vars(captured.campaign)
        assert case.stimuli == captured.stimuli
        assert case.summary_context == captured.summary_context
        assert case.global_summary == captured.global_summary
        assert case.recall == captured.recall
    assert coherent.reconstructed is True and coherent.derived is False
    assert conflict.reconstructed is False
    assert conflict.history == captured.history
    assert coherent.history and coherent.history != captured.history
    assert "You stand at the Shrine of First Light" in coherent.history[-1]["content"]
    assert "You stand at the threshold" in str(conflict.history)


def test_travel_cases_send_identical_prompt_tools_and_action_but_different_history() -> None:
    from live_calls import dm_request

    from app.ai.router import ModelConfig

    config = ModelConfig("openrouter", "model:free", 60000)
    coherent = dm_request(scenarios.load("travel-coherent"), "travel_move", config)
    conflict = dm_request(scenarios.load("travel-conflict"), "travel_move", config)
    coherent_messages = coherent.pop("messages")
    conflict_messages = conflict.pop("messages")

    assert coherent == conflict
    assert coherent_messages != conflict_messages
    assert (
        coherent_messages[-1]
        == conflict_messages[-1]
        == {
            "role": "user",
            "content": "I follow the forest path east toward Thornhaven.",
        }
    )
    assert 'location="Shrine of First Light"' in coherent["system_prompt"]
    assert any(tool["function"]["name"] == "move_to" for tool in coherent["tools"])


def test_long_coherent_travel_is_ten_realistically_sized_turns_with_the_same_inputs() -> None:
    from live_calls import dm_request

    from app.ai.router import ModelConfig

    short = scenarios.load("travel-coherent")
    long = scenarios.load("travel-coherent-long")
    assert long.name == "travel-coherent-long"
    assert long.reconstructed is True and long.derived is False
    assert vars(long.campaign) == vars(short.campaign)
    assert long.stimuli == short.stimuli
    assert long.summary_context == short.summary_context
    assert long.global_summary == short.global_summary
    assert long.recall == short.recall
    assert len(long.history) == 20
    assert [message["role"] for message in long.history] == ["user", "assistant"] * 10
    assert all(1000 <= len(message["content"]) <= 1800 for message in long.history[1::2])

    config = ModelConfig("openrouter", "model:free", 60000)
    short_request = dm_request(short, "travel_move", config)
    long_request = dm_request(long, "travel_move", config)
    short_messages = short_request.pop("messages")
    long_messages = long_request.pop("messages")
    assert short_request == long_request
    assert short_messages[-1] == long_messages[-1]


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
