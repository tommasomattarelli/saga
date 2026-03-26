from app.ai.prompts.companion import build_companion_prompt
from app.ai.prompts.npc import build_npc_prompt
from app.ai.prompts.world import build_world_sim_prompt


def test_build_companion_prompt():
    data = {
        "name": "Eldrin",
        "personality": "Stoic and loyal",
        "background": "Fallen knight",
        "loyalty": 8,
        "trust": 7,
        "mood": "determined",
    }
    prompt = build_companion_prompt(data)
    assert "Eldrin" in prompt
    assert "Stoic and loyal" in prompt
    assert "Fallen knight" in prompt
    assert "8/10" in prompt
    assert "determined" in prompt


def test_build_npc_prompt():
    data = {
        "name": "Bob",
        "role": "Innkeeper",
        "location": "The Prancing Pony",
        "goals": ["Make money"],
        "personality": {"traits": ["grumpy"], "fears": ["Bandits"], "secrets": ["Hides stolen goods"]},
        "disposition_toward_player": -50,
    }
    prompt = build_npc_prompt(data, player_action="I enter the inn", dm_narration="You push open the door.")
    assert "Bob" in prompt
    assert "Innkeeper" in prompt
    assert "The Prancing Pony" in prompt
    assert "Make money" in prompt
    assert "Bandits" in prompt
    assert "Hides stolen goods" in prompt
    assert "-50" in prompt
    assert "I enter the inn" in prompt


def test_build_world_sim_prompt():
    world_state = {
        "time": {"time_of_day": "evening"},
        "weather": "rainy and cold",
        "factions": {"The Thieves Guild": {"power": 5}},
    }
    prompt = build_world_sim_prompt(world_state, turn_number=42)
    assert "evening" in prompt
    assert "rainy and cold" in prompt
    assert "Turn: 42" in prompt
    assert "The Thieves Guild" in prompt
