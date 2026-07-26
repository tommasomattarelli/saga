from app.ai.prompts.npc import build_npc_prompt
from app.models.psychology import PsychologyDef

AXIS = {
    "range": [-100, 100],
    "default": 0,
    "bands": [{"min": -100, "label": "shamed"}, {"min": 0, "label": "honored"}],
}


def test_build_npc_prompt_renders_all_traits():
    # ADR 0009 G3: the NPC playing itself sees every trait, world-defined ones too.
    data = {
        "name": "Bob",
        "location_name": "The Prancing Pony",
        "traits": {
            "role": "Innkeeper",
            "motivation": "Make money",
            "secret": "Hides stolen goods",
            "dreads": "Bandits",
            "honor_code": "never cheats a guest",
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
    assert "Honor code: never cheats a guest" in prompt
    assert "I enter the inn" in prompt
    # ADR 0005 D1: number + band label, full axis list, contract + cap taught
    assert "trust: -50 (betrayed-wary)" in prompt
    assert "respect: 0 (neutral)" in prompt
    assert "axis_changes" in prompt
    assert "trust, respect, affection, fear" in prompt
    assert "±10" in prompt


def test_empty_traits_hidden_without_fill_guidance():
    data = {"name": "Bob", "traits": {"role": "Innkeeper", "secret": ""}}
    prompt = build_npc_prompt(data)
    assert "Secret:" not in prompt
    assert "Not yet established" not in prompt


def test_rich_fill_guidance_lists_empty_traits():
    # ADR 0009 D2: rich level → invent missing facts in character.
    data = {"name": "Bob", "traits": {"role": "Innkeeper", "secret": "", "ideal": ""}}
    prompt = build_npc_prompt(data, fill_empty_traits=True)
    assert "Not yet established about you: secret, ideal" in prompt
    assert "stay consistent" in prompt


def test_location_falls_back_to_unknown_never_uuid():
    # ADR 0009 S3: a raw node uuid must never leak into the prompt.
    data = {"name": "Bob", "location": "3fa8c2e1-0000-0000-0000-000000000000", "traits": {}}
    prompt = build_npc_prompt(data)
    assert "3fa8c2e1" not in prompt
    assert "Location: Unknown" in prompt


def test_npc_prompt_world_defined_axes():
    pdef = PsychologyDef(max_delta_per_turn=5, axes={"honor": AXIS})
    prompt = build_npc_prompt({"name": "Kira", "psychology": {"honor": 20}}, psychology=pdef)
    assert "honor: 20 (honored)" in prompt
    assert "trust" not in prompt
    assert "±5" in prompt
