"""Unit tests for private helpers in app/core/dm/dm_tools_executor.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _fixed_roll(die: int, draw: int):
    """Drive the real resolver instead of mocking its result (std 5)."""
    return (
        patch("app.core.dice.random.randint", return_value=die),
        patch("app.core.dice.draw_difficulty_modifier", return_value=draw),
    )


class TestHandleDice:
    def test_reports_the_level_and_the_draw_never_a_dc(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(15, -3)
        with die, draw:
            result_str, roll_data, _ = _handle_dice(
                {"stat": "STR", "check": "strength_check", "difficulty": "hard"},
                {"abilities": {"STR": 14}},
                step=0,
                narration_segments=[],
            )

        assert "DC" not in result_str
        assert "hard" in result_str
        entry = roll_data["Strength Check"]
        assert "dc" not in entry
        assert entry["difficulty"] == "hard"
        assert entry["difficulty_draw"] == -3
        assert entry["total"] == 15 + 2 - 3  # die + STR modifier + draw
        assert entry["outcome"] == "partial_success"

    def test_an_absent_difficulty_falls_back_to_normal(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(10, 0)
        with die, draw:
            _, roll_data, _ = _handle_dice(
                {"stat": "INT", "check": "lore"}, {}, step=0, narration_segments=[]
            )
        assert roll_data["Lore"]["difficulty"] == "normal"

    def test_context_appended_when_reason_provided(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(10, 0)
        with die, draw:
            result_str, _, _ = _handle_dice(
                {"stat": "DEX", "difficulty": "normal", "reason": "dodge arrow"},
                {"abilities": {}},
                step=0,
                narration_segments=[],
            )
        assert "dodge arrow" in result_str

    def test_no_context_when_no_reason(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(8, 0)
        with die, draw:
            result_str, _, _ = _handle_dice(
                {"stat": "INT", "difficulty": "easy"}, {}, step=0, narration_segments=[]
            )
        assert "Context:" not in result_str

    def test_uses_stat_score_from_char_data(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(10, 0)
        with die, draw:  # WIS 16 → modifier = (16-10)//2 = 3
            _, roll_data, _ = _handle_dice(
                {"stat": "WIS", "check": "insight", "difficulty": "normal"},
                {"abilities": {"WIS": 16}},
                step=0,
                narration_segments=[],
            )
        assert roll_data["Insight"]["modifier"] == 3

    def test_full_name_ability_key_from_frontend(self):
        # The frontend persists abilities under full lowercase names ("dexterity"),
        # while request_dice passes the abbreviation ("DEX"): the reader must bridge.
        from app.core.dm.dm_tools_executor import _handle_dice

        die, draw = _fixed_roll(10, 0)
        with die, draw:
            _, roll_data, _ = _handle_dice(
                {"stat": "DEX", "check": "sleight", "difficulty": "normal"},
                {"abilities": {"dexterity": 16}},
                step=0,
                narration_segments=[],
            )
        assert roll_data["Sleight"]["modifier"] == 3

    def test_segment_dice_is_populated(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        segments: list[dict] = []
        die, draw = _fixed_roll(15, 0)
        with die, draw:
            _handle_dice(
                {"stat": "CON", "check": "con_check", "difficulty": "normal"},
                {},
                step=2,
                narration_segments=segments,
            )

        assert segments[0]["step"] == 2
        assert segments[0]["dice"] is not None


class TestHandleDiceHazard:
    """A hazard is an enemy without legs: the tier doses the damage (ADR 0003 B7)."""

    def test_a_failed_reaction_roll_takes_the_full_draw(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        char_data = {"hp": {"current": 100, "max": 100}}
        die, draw = _fixed_roll(2, 0)  # total 2 → hard_failure
        with die, draw, patch("app.core.health.random.uniform", return_value=0.50):
            result_str, roll_data, char_data = _handle_dice(
                {"stat": "DEX", "check": "dodge", "difficulty": "hard", "hazard_class": "deadly"},
                char_data,
                step=0,
                narration_segments=[],
            )

        assert roll_data["Dodge"]["hazard_damage"] == 50
        assert char_data["hp"]["current"] == 50
        assert "50 damage" in result_str

    def test_a_full_success_dodges_it_outright(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        char_data = {"hp": {"current": 100, "max": 100}}
        die, draw = _fixed_roll(18, 0)  # total 18 → full_success
        with die, draw:
            _, roll_data, char_data = _handle_dice(
                {"stat": "DEX", "check": "dodge", "difficulty": "hard", "hazard_class": "deadly"},
                char_data,
                step=0,
                narration_segments=[],
            )

        assert roll_data["Dodge"]["hazard_damage"] == 0
        assert char_data["hp"]["current"] == 100

    def test_a_plain_check_never_touches_hp(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        char_data = {"hp": {"current": 30, "max": 100}}
        die, draw = _fixed_roll(1, 0)  # natural 1, the worst possible outcome
        with die, draw:
            _, roll_data, char_data = _handle_dice(
                {"stat": "CHA", "check": "persuasion", "difficulty": "very_hard"},
                char_data,
                step=0,
                narration_segments=[],
            )

        assert "hazard_damage" not in roll_data["Persuasion"]
        assert char_data["hp"]["current"] == 30


class TestHandleNpcResults:
    def test_returns_dialogue_string(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Aria"
        npc_result.dialogue = "Greetings, traveler."
        npc_result.action = None
        npc_result.axis_changes = {}

        result_str, ws, cd = _handle_npc_results(
            npc_name="Aria",
            npc_results=[npc_result],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state={},
            char_data={},
        )

        assert "Aria" in result_str
        assert "Greetings, traveler." in result_str

    def test_action_appended_to_dialogue(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Guard"
        npc_result.dialogue = "Halt!"
        npc_result.action = "blocks the path"
        npc_result.axis_changes = {}

        result_str, _, _ = _handle_npc_results(
            npc_name="Guard",
            npc_results=[npc_result],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state={},
            char_data={},
        )

        assert "[blocks the path]" in result_str

    def test_empty_results_returns_no_response(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        result_str, _, _ = _handle_npc_results(
            npc_name="Ghost",
            npc_results=[],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state={},
            char_data={},
        )

        assert "Ghost does not respond." in result_str

    def test_updates_npc_world_state_history(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Merchant"
        npc_result.dialogue = "Wares for sale!"
        npc_result.action = None
        npc_result.axis_changes = {}

        world_state = {"npcs": {"Merchant": {"name": "Merchant", "role": "trader"}}}
        _handle_npc_results(
            npc_name="Merchant",
            npc_results=[npc_result],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state=world_state,
            char_data={},
        )

        assert "last_interactions" in world_state["npcs"]["Merchant"]
        assert '"Wares for sale!"' in world_state["npcs"]["Merchant"]["last_interactions"]

    def test_history_capped_at_3(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        existing_history = ['"old1"', '"old2"', '"old3"']
        world_state = {
            "npcs": {"NPC": {"name": "NPC", "last_interactions": existing_history.copy()}}
        }

        npc_result = MagicMock()
        npc_result.npc_name = "NPC"
        npc_result.dialogue = "new line"
        npc_result.action = None
        npc_result.axis_changes = {}

        _handle_npc_results(
            npc_name="NPC",
            npc_results=[npc_result],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state=world_state,
            char_data={},
        )

        history = world_state["npcs"]["NPC"]["last_interactions"]
        assert len(history) == 3
        assert '"new line"' in history

    def test_axis_changes_applied_with_world_config(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Elder"
        npc_result.dialogue = "You have earned my trust."
        npc_result.action = None
        npc_result.axis_changes = {"trust": 8}

        baseline = {
            "taxonomy": {"psychology": {"axes": {"trust": {"bands": [{"min": 0, "label": "x"}]}}}}
        }
        with patch("app.core.dm.dm_tools_executor.apply_typed_updates") as mock_updates:
            mock_updates.return_value = ({}, {})
            _handle_npc_results(
                npc_name="Elder",
                npc_results=[npc_result],
                npc_dialogues=[],
                narration_segments=[],
                step=0,
                world_state={},
                char_data={},
                baseline=baseline,
            )
            mock_updates.assert_called_once()
            update = mock_updates.call_args[0][2][0]
            assert update["key"] == "npc_psychology"
            assert update["changes"] == {"trust": 8}
            assert update["config"] == baseline["taxonomy"]["psychology"]

    def test_zero_changes_still_apply_to_flip_met_player(self):
        # ADR 0005 B3: a completed dialogue is an interaction — met is met.
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Farmer"
        npc_result.dialogue = "Good day."
        npc_result.action = None
        npc_result.axis_changes = {}

        world_state = {"npcs": {"Farmer": {"name": "Farmer", "met_player": False}}}
        _, ws, _ = _handle_npc_results(
            npc_name="Farmer",
            npc_results=[npc_result],
            npc_dialogues=[],
            narration_segments=[],
            step=0,
            world_state=world_state,
            char_data={},
        )
        assert ws["npcs"]["Farmer"]["met_player"] is True

    def test_npc_dialogues_list_updated(self):
        from app.core.dm.dm_tools_executor import _handle_npc_results

        npc_result = MagicMock()
        npc_result.npc_name = "Wizard"
        npc_result.dialogue = "Magic!"
        npc_result.action = "waves wand"
        npc_result.axis_changes = {}

        npc_dialogues: list[dict] = []
        _handle_npc_results(
            npc_name="Wizard",
            npc_results=[npc_result],
            npc_dialogues=npc_dialogues,
            narration_segments=[],
            step=0,
            world_state={},
            char_data={},
        )

        assert len(npc_dialogues) == 1
        assert npc_dialogues[0]["npc_name"] == "Wizard"
        assert npc_dialogues[0]["dialogue"] == "Magic!"
        assert npc_dialogues[0]["action"] == "waves wand"
