from app.ai.prompts.npc import build_npc_prompt


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
        "disposition_toward_player": -50,
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
    assert "-50" in prompt
    assert "I enter the inn" in prompt
