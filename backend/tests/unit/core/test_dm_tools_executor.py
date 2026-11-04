"""Unit tests for private helpers in app/core/dm/dm_tools_executor.py."""

from __future__ import annotations

from unittest.mock import patch

from app.ai.npc_outcomes import NPCSpeaking


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


class TestNpcResults:
    def test_apply_actor_effects_uses_uuid_target_and_baseline_taxonomy(self):
        from app.core.dm.npc_results import apply_actor_effects

        baseline = {"taxonomy": {"psychology": {"axes": {"trust": {"default": 0}}}}}
        with patch("app.core.dm.npc_results.apply_typed_updates", return_value=({}, {})) as update:
            apply_actor_effects(
                "npc-uuid", NPCSpeaking("Elder", (), axis_changes={"trust": 8}), {}, {}, baseline
            )
        record = update.call_args.args[2][0]
        assert record["key"] == "npc_psychology"
        assert record["target"] == "npc-uuid"
        assert record["changes"] == {"trust": 8}
        assert record["config"] == baseline["taxonomy"]["psychology"]

    def test_flush_history_groups_typed_public_results_by_npc(self):
        from app.core.dm.npc_context import NPCBeat, PublicNPCResult
        from app.core.dm.npc_results import flush_interaction_history

        world_state = {"npcs": {"id-1": {"last_interactions": ['"old"']}}}
        beat = NPCBeat(
            0,
            frozenset(),
            "square",
            (
                PublicNPCResult("id-1", "Merchant", ("Wares!",), "opens a crate"),
                PublicNPCResult("missing", "Ghost", (), None),
            ),
        )
        with patch("app.core.dm.npc_results.get_gameplay_config") as config:
            config.return_value.npc_last_interactions_kept = 3
            flush_interaction_history(world_state, [beat])
        assert world_state["npcs"]["id-1"]["last_interactions"] == [
            '"old"',
            '"Wares!" opens a crate',
        ]
