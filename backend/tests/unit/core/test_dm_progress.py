from langchain_core.messages import AIMessage

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


async def test_rejected_closing_calls_each_keep_their_provider_result_id():
    from app.core.dm.dm_tools_executor import tools_node

    calls = [
        {"id": f"call-{i}", "name": name, "args": {}}
        for i, name in enumerate(["invoke_npc", "request_dice", "attack"])
    ]
    result = await tools_node(
        {
            "messages": [AIMessage(content="", tool_calls=calls)],
            "world_state": {},
            "char_data": {},
            "step_count": 8,
            "max_agent_steps": 8,
            "tool_events": [],
            "dice_results": [],
            "npc_dialogues": [],
            "called_npcs": [],
            "scene_mood": "neutral",
            "time_passed_minutes": 0,
            "narration_segments": [],
            "narration": "",
            "allowed_tools": ["advance_time", "log_event", "set_scene_mood"],
            "closing_step": True,
        }
    )
    assert {message.tool_call_id for message in result["messages"]} == {
        call["id"] for call in calls
    }
    assert len(result["messages"]) == len(calls)
    assert result["dice_results"] == result["npc_dialogues"] == result["tool_events"] == []
    assert result["world_state"] == result["char_data"] == {}
