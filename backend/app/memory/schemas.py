"""Pydantic schemas for world state sub-objects (NPC, Companion)."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class NPCPersonality(BaseModel):
    traits: list[str] = []
    values: list[str] = []
    fears: list[str] = []
    secrets: list[str] = []


class NPCProfile(BaseModel):
    name: str
    role: str = ""
    location: str = ""
    personality: NPCPersonality = NPCPersonality()
    disposition_toward_player: int = 0
    goals: list[str] = []
    memory: list[str] = []

    @field_validator("disposition_toward_player")
    @classmethod
    def clamp_disposition(cls, v: int) -> int:
        return max(-100, min(100, v))

    model_config = {"extra": "allow"}


class CompanionProfile(NPCProfile):
    loyalty: int = 50
    personal_quest_stage: str = "dormant"
    opinions: dict[str, str] = {}
    combat_style: str = "balanced"
    backstory_hooks: list[str] = []

    @field_validator("loyalty")
    @classmethod
    def clamp_loyalty(cls, v: int) -> int:
        return max(0, min(100, v))
