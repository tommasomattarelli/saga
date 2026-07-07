from app.ai.prompts.npc import build_npc_prompt
from app.models.psychology import PsychologyDef

AXIS = {
    "range": [-100, 100],
    "default": 0,
    "bands": [{"min": -100, "label": "shamed"}, {"min": 0, "label": "honored"}],
}


def test_build_npc_prompt():
    data = {
        "name": "Bob",
        "role": "Innkeeper",
        "location": "The Prancing Pony",
        "goals": ["Make money"],
        "personality": {
            "traits": ["grumpy"],
            "fears": ["Bandits"],
            "secrets": ["Hides stolen goods"],
        },
        "psychology": {"trust": -50},
    }
    prompt = build_npc_prompt(
        data, player_action="I enter the inn", dm_narration="You push open the door."
    )
    assert "Bob" in prompt
    assert "Innkeeper" in prompt
    assert "The Prancing Pony" in prompt
    assert "Make money" in prompt
    assert "Bandits" in prompt
    assert "Hides stolen goods" in prompt
    assert "I enter the inn" in prompt
    # ADR 0005 D1: number + band label, full axis list, contract + cap taught
    assert "trust: -50 (betrayed-wary)" in prompt
    assert "respect: 0 (neutral)" in prompt
    assert "axis_changes" in prompt
    assert "trust, respect, affection, fear" in prompt
    assert "±10" in prompt


def test_npc_prompt_world_defined_axes():
    pdef = PsychologyDef(max_delta_per_turn=5, axes={"honor": AXIS})
    prompt = build_npc_prompt({"name": "Kira", "psychology": {"honor": 20}}, psychology=pdef)
    assert "honor: 20 (honored)" in prompt
    assert "trust" not in prompt
    assert "±5" in prompt
