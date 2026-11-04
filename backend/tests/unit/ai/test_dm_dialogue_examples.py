import pytest

from app.ai.prompts.dm import build_dm_system_prompt
from app.ai.prompts.obligations import compose_obligations
from app.models.campaign import Campaign


@pytest.mark.parametrize("language", ["en", "it"])
@pytest.mark.parametrize(
    ("allowed", "closing"),
    [(set(), False), ({"invoke_npc"}, False), ({"advance_time", "log_event"}, True)],
)
def test_composition_examples_remain_in_dm_core_independently_of_actor_tool_availability(
    language: str,
    allowed: set[str],
    closing: bool,
) -> None:
    campaign = Campaign(world_state={}, character_data={}, quests={}, language=language)
    prompt = build_dm_system_prompt(campaign, allowed_tools=allowed, closing=closing)
    core = prompt.split("<dm_core>", 1)[1].split("</dm_core>", 1)[0]
    engine = prompt.split("<engine>", 1)[1].split("</engine>", 1)[0]

    assert "DIALOGUE COMPOSITION:" in core
    assert prompt.count("DIALOGUE COMPOSITION:") == 1
    assert "GOOD DM:" in core and "BAD DM:" in core
    assert "DIALOGUE COMPOSITION:" not in engine
    assert ('tool="invoke_npc"' in prompt) == ("invoke_npc" in allowed)
    assert "invoke_npc(name=" not in core
    assert "{campaign_language}" not in prompt
    assert ("CLOSING STEP:" in prompt) == closing


def test_composition_examples_contrast_copying_omission_and_invented_speech() -> None:
    campaign = Campaign(world_state={}, character_data={}, quests={}, language="it")
    prompt = build_dm_system_prompt(campaign, allowed_tools=set(), closing=True)

    assert "Example 1: placement" in prompt
    assert '[[npc:Lysa:1]] "I do not have the key."' in prompt
    assert "[[npc:Lysa:1]] I do not have the key." in prompt
    assert "Example 2: complete beat in Italian (it)" in prompt
    assert (
        "GOOD DM: Lysa posa il sigillo. [[npc:Lysa:1]] [[npc:Lysa:2]] Neri arretra. [[npc:Neri:1]]"
        in prompt
    )
    assert "Example 3: closing with an existing result" in prompt
    assert "A room for ten coins" in prompt
    assert "Each example is independent" in prompt


def test_actor_tool_obligation_keeps_call_policy_without_duplicating_placement_examples() -> None:
    obligation = compose_obligations({"invoke_npc"})

    assert "parallel beat" in obligation and "subsequent beat" in obligation
    assert "Example exchange:" in obligation
    assert "Intentional silence is valid" in obligation
    assert "without retrying" in obligation
    assert "Example 1: placement" not in obligation
    assert "DIALOGUE PROTOCOL:" not in obligation
