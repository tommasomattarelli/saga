from app.core.dm.progress import StepProgress
from app.models.quest import QuestRegistry


def test_nested_mutations_count_even_when_the_tool_description_is_repeated():
    world = {"npcs": {"npc": {"condition": "waiting"}}}
    progress = StepProgress(world, {}, QuestRegistry(), [])
    progress.record("update_npc", {"name": "Lyra"}, "Updated.")
    world["npcs"]["npc"]["condition"] = "alert"
    assert progress.changed(world, {}, QuestRegistry())


def test_playable_results_ignore_request_id_and_step_but_compare_arguments_and_result():
    progress = StepProgress({}, {}, QuestRegistry(), [])
    progress.record(
        "request_dice",
        {"difficulty": "normal", "stat": "DEX", "check": "Stealth"},
        {"roll": 4},
        playable=True,
    )
    assert progress.changed({}, {}, QuestRegistry())
    next_step = StepProgress({}, {}, QuestRegistry(), progress.fingerprints)
    next_step.record(
        "request_dice",
        {"check": "Stealth", "stat": "DEX", "difficulty": "normal"},
        {"roll": 4},
        playable=True,
    )
    assert not next_step.changed({}, {}, QuestRegistry())
    next_step.record(
        "request_dice",
        {"check": "Stealth", "stat": "DEX", "difficulty": "normal"},
        {"roll": 12},
        playable=True,
    )
    assert next_step.changed({}, {}, QuestRegistry())


def test_tool_defaults_are_normalized_and_state_change_wins_over_repetition():
    first = StepProgress({"clock": {"total_minutes": 480}}, {}, QuestRegistry(), [])
    first.record("advance_time", {"minutes": 5}, "Time advanced.")
    after = {"clock": {"total_minutes": 485}}
    assert first.changed(after, {}, QuestRegistry())
    second = StepProgress(after, {}, QuestRegistry(), first.fingerprints)
    second.record("advance_time", {"minutes": 5}, "Time advanced.")
    assert second.changed({"clock": {"total_minutes": 490}}, {}, QuestRegistry())


def test_rejections_do_not_count_even_the_first_time():
    progress = StepProgress({}, {}, QuestRegistry(), [])
    progress.record("move_to", {"location": "Nowhere"}, "Move rejected.")
    assert not progress.changed({}, {}, QuestRegistry())


def test_omitted_tool_defaults_do_not_create_fake_novelty():
    first = StepProgress({}, {}, QuestRegistry(), [])
    first.record("invoke_npc", {"name": "Lyra"}, {"dialogue": "Hello."}, playable=True)
    second = StepProgress({}, {}, QuestRegistry(), first.fingerprints)
    second.record(
        "invoke_npc", {"name": "Lyra", "context": ""}, {"dialogue": "Hello."}, playable=True
    )
    assert not second.changed({}, {}, QuestRegistry())
