"""Unit tests for private helpers in app/core/dm/dm_tools_executor.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestHandleDice:
    def test_returns_result_str_and_roll_data(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20+2"
        mock_roll.rolls = [15]
        mock_roll.modifier = 2
        mock_roll.total = 17

        mock_dice_result = {
            "roll": mock_roll,
            "success": True,
            "outcome": "success",
            "is_critical": False,
        }

        with patch("app.core.dm.dm_tools_executor.ability_check", return_value=mock_dice_result):
            args = {
                "dc": 15,
                "stat": "STR",
                "check": "strength_check",
                "reason": "lifting boulder",
            }
            char_data = {"abilities": {"STR": 14}}
            segments: list[dict] = []

            result_str, roll_data = _handle_dice(
                args, char_data, step=0, narration_segments=segments
            )

        assert "DC 15" in result_str
        assert "success" in result_str
        assert "Strength Check" in roll_data
        assert roll_data["Strength Check"]["dc"] == 15
        assert roll_data["Strength Check"]["success"] is True

    def test_context_appended_when_reason_provided(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20"
        mock_roll.rolls = [10]
        mock_roll.modifier = 0
        mock_roll.total = 10

        mock_dice_result = {
            "roll": mock_roll,
            "success": False,
            "outcome": "failure",
            "is_critical": False,
        }

        with patch("app.core.dm.dm_tools_executor.ability_check", return_value=mock_dice_result):
            args = {"dc": 12, "stat": "DEX", "reason": "dodge arrow"}
            char_data = {"abilities": {}}
            result_str, _ = _handle_dice(args, char_data, step=0, narration_segments=[])

        assert "dodge arrow" in result_str

    def test_no_context_when_no_reason(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20"
        mock_roll.rolls = [8]
        mock_roll.modifier = 0
        mock_roll.total = 8

        mock_dice_result = {
            "roll": mock_roll,
            "success": False,
            "outcome": "failure",
            "is_critical": False,
        }

        with patch("app.core.dm.dm_tools_executor.ability_check", return_value=mock_dice_result):
            args = {"dc": 10, "stat": "INT"}
            char_data = {}
            result_str, _ = _handle_dice(args, char_data, step=0, narration_segments=[])

        assert "Context:" not in result_str

    def test_uses_stat_score_from_char_data(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20+3"
        mock_roll.rolls = [10]
        mock_roll.modifier = 3
        mock_roll.total = 13

        mock_dice_result = {
            "roll": mock_roll,
            "success": True,
            "outcome": "success",
            "is_critical": False,
        }

        captured_modifier = {}

        def mock_ability_check(modifier, dc):
            captured_modifier["value"] = modifier
            return mock_dice_result

        with patch("app.core.dm.dm_tools_executor.ability_check", side_effect=mock_ability_check):
            # WIS 16 → modifier = (16-10)//2 = 3
            args = {"dc": 10, "stat": "WIS"}
            char_data = {"abilities": {"WIS": 16}}
            _handle_dice(args, char_data, step=0, narration_segments=[])

        assert captured_modifier["value"] == 3

    def test_full_name_ability_key_from_frontend(self):
        # The frontend persists abilities under full lowercase names ("dexterity"),
        # while request_dice passes the abbreviation ("DEX"): the reader must bridge.
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20+3"
        mock_roll.rolls = [10]
        mock_roll.modifier = 3
        mock_roll.total = 13

        mock_dice_result = {
            "roll": mock_roll,
            "success": True,
            "outcome": "success",
            "is_critical": False,
        }

        captured_modifier = {}

        def mock_ability_check(modifier, dc):
            captured_modifier["value"] = modifier
            return mock_dice_result

        with patch("app.core.dm.dm_tools_executor.ability_check", side_effect=mock_ability_check):
            # dexterity 16 → modifier = (16-10)//2 = 3
            args = {"dc": 10, "stat": "DEX"}
            char_data = {"abilities": {"dexterity": 16}}
            _handle_dice(args, char_data, step=0, narration_segments=[])

        assert captured_modifier["value"] == 3

    def test_segment_dice_is_populated(self):
        from app.core.dm.dm_tools_executor import _handle_dice

        mock_roll = MagicMock()
        mock_roll.expression = "1d20"
        mock_roll.rolls = [15]
        mock_roll.modifier = 0
        mock_roll.total = 15

        mock_dice_result = {
            "roll": mock_roll,
            "success": True,
            "outcome": "success",
            "is_critical": False,
        }

        with patch("app.core.dm.dm_tools_executor.ability_check", return_value=mock_dice_result):
            segments: list[dict] = []
            args = {"dc": 10, "stat": "CON", "check": "con_check"}
            _handle_dice(args, {}, step=2, narration_segments=segments)

        assert segments[0]["step"] == 2
        assert segments[0]["dice"] is not None


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
