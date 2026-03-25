"""Pydantic schema for structured DM output."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, field_validator


class SceneMood(StrEnum):
    CALM_EXPLORATION = "calm_exploration"
    TENSE_ANTICIPATION = "tense_anticipation"
    COMBAT_FURY = "combat_fury"
    STEALTH_DANGER = "stealth_danger"
    SOCIAL_INTRIGUE = "social_intrigue"
    MELANCHOLIC_REFLECTION = "melancholic_reflection"
    TRIUMPHANT_VICTORY = "triumphant_victory"
    DREAD_HORROR = "dread_horror"
    WONDER_DISCOVERY = "wonder_discovery"
    MOURNING_LOSS = "mourning_loss"
    NEUTRAL = "neutral"


class DiceRequest(BaseModel):
    name: str
    dc: int = 10
    modifier: int = 0
    advantage: bool = False
    disadvantage: bool = False


class CompanionAction(BaseModel):
    name: str
    action: str


class WorldUpdate(BaseModel):
    key: str
    value: str | int | float | bool | dict | list


class DMResponse(BaseModel):
    narration: str = ""
    invoke_npcs: list[str] = []
    dice_required: list[DiceRequest] | None = None
    scene_mood: SceneMood = SceneMood.NEUTRAL
    # dialogue 1-5, exploration 10-30, travel 30-480, rest 60-480
    time_passed_minutes: int = 5
    companion_actions: dict[str, str] | None = None
    world_updates: dict | None = None
    suggested_actions: list[str] | None = None
    ambient_detail: str | None = None
    scene_image_prompt: str | None = None

    @field_validator("scene_mood", mode="before")
    @classmethod
    def coerce_scene_mood(cls, v: str | None) -> str:
        if v is None:
            return SceneMood.NEUTRAL
        try:
            return SceneMood(v.lower().strip())
        except ValueError:
            return SceneMood.NEUTRAL

    model_config = {"extra": "ignore"}
