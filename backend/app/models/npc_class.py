"""ADR 0003 B3b — world-defined NPC archetypes carrying a statblock template.

The free-text `role` trait ("imperatore", "panettiere") stays descriptive; the class
carries the mechanics, so a butcher can never hold general-grade numbers. Coarse and
few by design — this is a vocabulary, not a bestiary.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from app.config_loader import load_saga_config
from app.core.dice import DifficultyLevel


class HpClass(StrEnum):
    WEAK = "weak"
    STANDARD = "standard"
    TOUGH = "tough"
    BOSS = "boss"


class DamageClass(StrEnum):
    UNARMED = "unarmed"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class NpcClassDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    hp_class: HpClass = HpClass.STANDARD
    defense: DifficultyLevel = DifficultyLevel.NORMAL
    damage_class: DamageClass = DamageClass.LIGHT
    attack_mod: int = 0

    @field_validator("attack_mod")
    @classmethod
    def _clamp(cls, value: int) -> int:
        low, high = load_saga_config()["combat"]["attack_mod_clamp"]
        return max(low, min(high, value))
