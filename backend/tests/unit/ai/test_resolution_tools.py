"""The LLM-facing resolution surface: classes and levels, never numbers (ADR 0003 D)."""

from app.ai.tools.dm_tools import Heal, RequestDice, execute_tool, get_tool, get_tool_schemas


def _props(tool_cls) -> dict:
    return tool_cls.to_openai_schema()["function"]["parameters"]["properties"]


def _world(minutes: int = 480) -> dict:
    return {
        "clock": {"total_minutes": minutes},
        "meta": {"current_location": "tavern"},
        "npcs": {
            "npc-1": {"name": "Mirella", "lifecycle": "alive", "location": "tavern"},
            "npc-2": {"name": "Corvo", "lifecycle": "alive", "location": "docks"},
            "npc-3": {"name": "Bram", "lifecycle": "dead", "location": "tavern"},
        },
    }


def _char(current: int = 10, max_hp: int = 40) -> dict:
    return {"name": "Lyra", "hp": {"current": current, "max": max_hp}}


class TestRequestDiceContract:
    def test_the_dc_is_gone(self):
        assert "dc" not in _props(RequestDice)

    def test_difficulty_is_offered_as_the_six_levels(self):
        assert _props(RequestDice)["difficulty"]["enum"] == [
            "trivial",
            "easy",
            "normal",
            "hard",
            "very_hard",
            "near_impossible",
        ]

    def test_situational_circumstances_are_binary(self):
        props = _props(RequestDice)
        assert props["advantage"]["type"] == "boolean"
        assert props["disadvantage"]["type"] == "boolean"

    def test_hazard_class_is_offered_as_classes(self):
        assert _props(RequestDice)["hazard_class"]["enum"] == ["minor", "serious", "deadly"]

    def test_a_dc_is_rejected_outright(self):
        result = execute_tool("request_dice", {"check": "stealth", "dc": 18}, {}, {})
        assert "failed" in result.description.lower()


class TestHealContract:
    def test_heal_takes_a_class_not_a_number(self):
        props = _props(Heal)
        assert props["heal_class"]["enum"] == ["minor", "strong", "full"]
        assert "amount" not in props
        assert "change" not in props

    def test_a_heal_amount_is_rejected_outright(self):
        result = execute_tool(
            "heal", {"healer": "Mirella", "target": "Lyra", "amount": 30}, _world(), _char()
        )
        assert "failed" in result.description.lower()


class TestNoToolWritesAFreeHpNumber:
    """The regression that keeps leak #2 closed (ADR 0003 §G)."""

    def test_update_hp_is_gone(self):
        assert get_tool("update_hp") is None
        assert "update_hp" not in {s["function"]["name"] for s in get_tool_schemas()}

    def test_the_removed_tool_reports_itself_unknown(self):
        result = execute_tool("update_hp", {"change": 50}, {}, _char())
        assert "unknown tool" in result.description.lower()


class TestHealGuards:
    """No resource economy until 0010/0012, so the bounds are mechanical (B7b)."""

    def test_a_healer_in_the_scene_heals(self):
        result = execute_tool(
            "heal",
            {"healer": "Mirella", "target": "Lyra", "heal_class": "full", "reason": "prayer"},
            _world(),
            _char(current=10, max_hp=40),
        )
        assert result.char_data["hp"]["current"] == 40

    def test_a_healer_elsewhere_cannot_reach_the_player(self):
        result = execute_tool(
            "heal",
            {"healer": "Corvo", "target": "Lyra", "heal_class": "full", "reason": "prayer"},
            _world(),
            _char(),
        )
        assert "not present" in result.description.lower()
        assert result.char_data["hp"]["current"] == 10

    def test_a_dead_healer_cannot_heal(self):
        result = execute_tool(
            "heal",
            {"healer": "Bram", "target": "Lyra", "heal_class": "full", "reason": "prayer"},
            _world(),
            _char(),
        )
        assert result.char_data["hp"]["current"] == 10

    def test_the_player_may_heal_themselves(self):
        result = execute_tool(
            "heal",
            {"healer": "Lyra", "target": "Lyra", "heal_class": "minor", "reason": "potion"},
            _world(),
            _char(),
        )
        assert result.char_data["hp"]["current"] > 10

    def test_heal_spam_hits_the_daily_cap(self):
        world, char = _world(), _char(current=1, max_hp=100)
        args = {"healer": "Mirella", "target": "Lyra", "heal_class": "full", "reason": "x"}
        for _ in range(3):
            result = execute_tool("heal", args, world, char)
            world, char = result.world_state, result.char_data
        capped = execute_tool("heal", args, world, char)
        assert "no more" in capped.description.lower()
        assert capped.world_state["dm_heals"]["used"] == 3
