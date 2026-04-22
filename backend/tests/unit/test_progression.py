"""Unit tests for app/core/progression.py."""

from __future__ import annotations

from app.core.progression import (
    LEVEL_THRESHOLDS,
    ProficiencyGain,
    apply_skill_use,
    check_level_up,
)


class TestCheckLevelUp:
    def test_returns_none_when_xp_below_threshold(self):
        assert check_level_up(0, 1) is None

    def test_returns_new_level_when_xp_meets_threshold(self):
        result = check_level_up(LEVEL_THRESHOLDS[1], 1)
        assert result == 2

    def test_returns_none_at_max_level(self):
        max_level = len(LEVEL_THRESHOLDS)
        result = check_level_up(9999999, max_level)
        assert result is None

    def test_level_1_threshold(self):
        assert check_level_up(299, 1) is None
        assert check_level_up(300, 1) == 2

    def test_level_2_threshold(self):
        assert check_level_up(899, 2) is None
        assert check_level_up(900, 2) == 3

    def test_very_high_xp_still_only_one_level(self):
        # Should still return level+1 not skip multiple levels
        result = check_level_up(999999, 5)
        assert result == 6


class TestApplySkillUse:
    def test_initialises_skill_data(self):
        char_data: dict = {}
        apply_skill_use(char_data, "stealth", 10)
        assert "skills" in char_data
        assert "stealth" in char_data["skills"]
        assert char_data["skills"]["stealth"]["uses"] == 1

    def test_increments_use_count(self):
        char_data: dict = {}
        apply_skill_use(char_data, "perception", 5)
        apply_skill_use(char_data, "perception", 5)
        assert char_data["skills"]["perception"]["uses"] == 2

    def test_accumulates_progress(self):
        char_data: dict = {}
        apply_skill_use(char_data, "athletics", 9)  # 9//3 = 3 progress
        assert char_data["skills"]["athletics"]["progress"] == 3

    def test_minimum_progress_is_1(self):
        char_data: dict = {}
        apply_skill_use(char_data, "lore", 0)  # 0//3 = 0 but max(1, 0) = 1
        assert char_data["skills"]["lore"]["progress"] == 1

    def test_returns_none_when_no_level_up(self):
        char_data: dict = {}
        result = apply_skill_use(char_data, "stealth", 1)
        assert result is None

    def test_returns_proficiency_gain_on_level_up(self):
        char_data: dict = {}
        # Level 0 threshold = 10, progress_gain with difficulty=30 → 10 per call → level up
        result = apply_skill_use(char_data, "stealth", 30)
        assert isinstance(result, ProficiencyGain)
        assert result.skill == "stealth"
        assert result.old_level == 0
        assert result.new_level == 1

    def test_level_up_resets_progress(self):
        char_data: dict = {}
        apply_skill_use(char_data, "combat", 30)  # 10 progress → level up
        assert char_data["skills"]["combat"]["progress"] == 0
        assert char_data["skills"]["combat"]["level"] == 1

    def test_higher_level_requires_more_progress(self):
        char_data = {"skills": {"archery": {"level": 2, "uses": 5, "progress": 0}}}
        # threshold at level 2 = 10 + 2*5 = 20 — need 2 calls of difficulty 30 (10 each)
        result1 = apply_skill_use(char_data, "archery", 30)
        assert result1 is None  # only 10 progress, threshold is 20
        result2 = apply_skill_use(char_data, "archery", 30)
        assert isinstance(result2, ProficiencyGain)
        assert result2.new_level == 3

    def test_proficiency_gain_message_format(self):
        char_data: dict = {}
        result = apply_skill_use(char_data, "persuasion", 30)
        assert result is not None
        assert "persuasion" in result.message
        assert "1" in result.message
