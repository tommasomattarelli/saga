from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OperationErrorReason = Literal[
    "invalid_arguments",
    "unavailable",
    "unknown_tool",
    "domain_rejection",
    "execution_failed",
    "npc_failed",
]


class OperationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class MessageResult(OperationModel):
    kind: Literal["message"] = "message"
    description: str = Field(min_length=1)


class ErrorResult(OperationModel):
    kind: Literal["error"] = "error"
    description: str = Field(min_length=1)
    reason: OperationErrorReason
    npc_id: str | None = None


class AttackResult(OperationModel):
    kind: Literal["attack"] = "attack"
    description: str = Field(min_length=1)
    attacker: str
    target: str
    outcome: Literal[
        "critical_failure",
        "hard_failure",
        "soft_failure",
        "partial_success",
        "full_success",
        "critical_success",
    ]
    damage: int = Field(ge=0)
    hp: int
    max_hp: int
    died: bool


class CheckRoll(OperationModel):
    expression: str
    rolls: list[int]
    modifier: int
    difficulty: Literal["trivial", "easy", "normal", "hard", "very_hard", "near_impossible"]
    difficulty_draw: int
    total: int
    success: bool
    outcome: Literal[
        "critical_failure",
        "hard_failure",
        "soft_failure",
        "partial_success",
        "full_success",
        "critical_success",
    ]
    is_critical: bool
    hazard_damage: int | None = Field(default=None, ge=0)


class CheckResult(OperationModel):
    kind: Literal["check"] = "check"
    description: str = Field(min_length=1)
    checks: dict[str, CheckRoll]


class NPCResult(OperationModel):
    kind: Literal["npc"] = "npc"
    description: str = Field(min_length=1)
    npc_id: str
    status: Literal["speaking", "silent", "failed", "created"]
    lines: list[str] = []
    action: str | None = None
    axis_changes: dict[str, int] = {}


class DeathResult(OperationModel):
    kind: Literal["death"] = "death"
    description: str = Field(min_length=1)
    action: Literal["alive", "near_death", "fate_intervention", "dead"]
    is_dead: bool
    fate_interventions_remaining: int | None = None
