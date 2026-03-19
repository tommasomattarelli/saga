"""Classless XP and proficiency-by-use system."""

from dataclasses import dataclass


@dataclass
class ProficiencyGain:
    """Result of a proficiency increase from use."""

    skill: str
    old_level: int
    new_level: int
    message: str


# XP thresholds for level up (cumulative)
LEVEL_THRESHOLDS = [
    0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000, 305000, 355000,
]


def check_level_up(current_xp: int, current_level: int) -> int | None:
    """Check if the character should level up. Returns new level or None."""
    if current_level >= len(LEVEL_THRESHOLDS):
        return None
    if current_xp >= LEVEL_THRESHOLDS[current_level]:
        return current_level + 1
    return None


def apply_skill_use(character_data: dict, skill: str, difficulty: int) -> ProficiencyGain | None:
    """Track skill usage and potentially increase proficiency.

    The more a skill is used, the better the character gets at it.
    Higher difficulty actions give more progress.
    """
    skills = character_data.setdefault("skills", {})
    skill_data = skills.setdefault(skill, {"level": 0, "uses": 0, "progress": 0})

    skill_data["uses"] += 1
    progress_gain = max(1, difficulty // 3)
    skill_data["progress"] += progress_gain

    # Every 10 progress points = 1 level (diminishing at higher levels)
    threshold = 10 + (skill_data["level"] * 5)
    if skill_data["progress"] >= threshold:
        old_level = skill_data["level"]
        skill_data["level"] += 1
        skill_data["progress"] = 0
        return ProficiencyGain(
            skill=skill,
            old_level=old_level,
            new_level=skill_data["level"],
            message=f"Your {skill} has improved to level {skill_data['level']}!",
        )
    return None
