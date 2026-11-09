from __future__ import annotations

from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import Field, JsonValue, field_validator, model_validator

from app.memory.operation_results import (
    AttackResult,
    CheckResult,
    DeathResult,
    ErrorResult,
    MessageResult,
    NPCResult,
    OperationModel,
)

OperationOutcome = Literal["succeeded", "rejected", "failed"]
OperationOrigin = Literal["tool", "npc", "finalization"]


class AbsentValue(OperationModel):
    presence: Literal["absent"] = "absent"


class PresentValue(OperationModel):
    presence: Literal["present"] = "present"
    value: JsonValue


PresenceValue = Annotated[AbsentValue | PresentValue, Field(discriminator="presence")]


class StateDelta(OperationModel):
    scope: Literal["world_state", "character_data", "quests"]
    path: tuple[str, ...] = Field(min_length=1)
    before: PresenceValue
    after: PresenceValue

    @field_validator("path", mode="before")
    @classmethod
    def freeze_path(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value


OperationResult = Annotated[
    MessageResult | ErrorResult | AttackResult | CheckResult | NPCResult | DeathResult,
    Field(discriminator="kind"),
]


class CreateNPCArguments(OperationModel):
    name: str
    npc_id: str


class InteractionArguments(OperationModel):
    npc_id: str


class DeathArguments(OperationModel):
    difficulty: str


class OperationPayload(OperationModel):
    origin: OperationOrigin
    name: str = Field(min_length=1)
    outcome: OperationOutcome
    arguments: dict[str, JsonValue]
    result: OperationResult
    deltas: tuple[StateDelta, ...]

    @field_validator("deltas", mode="before")
    @classmethod
    def freeze_deltas(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        if self.outcome != "succeeded":
            if not isinstance(self.result, ErrorResult):
                raise ValueError("Unsuccessful operations require an explicit error result")
            failed = self.result.reason in {"execution_failed", "npc_failed"}
            if failed != (self.outcome == "failed"):
                raise ValueError("Error reason does not match the execution outcome")
            if self.result.reason in {"invalid_arguments", "unknown_tool", "unavailable"}:
                if self.origin == "tool" or (self.origin == "npc" and self.name == "invoke_npc"):
                    return self
                raise ValueError("Invalid operation origin")
        if self.origin == "npc" and self.name == "create_npc":
            CreateNPCArguments.model_validate(self.arguments)
        elif self.origin == "finalization" and self.name == "record_interactions":
            InteractionArguments.model_validate(self.arguments)
        elif self.origin == "finalization" and self.name == "check_player_death":
            DeathArguments.model_validate(self.arguments)
        else:
            from app.ai.tools.dm_tools import get_tool

            tool = get_tool(self.name)
            if (
                tool is None
                or self.origin == "finalization"
                or (self.origin == "npc" and self.name != "invoke_npc")
                or (self.origin == "tool" and self.name == "invoke_npc")
            ):
                raise ValueError("Unknown operation")
            tool.model_validate(self.arguments)
        if self.outcome == "succeeded":
            expected = {
                "attack": "attack",
                "request_dice": "check",
                "invoke_npc": "npc",
                "create_npc": "npc",
                "check_player_death": "death",
            }.get(self.name, "message")
            if self.result.kind != expected:
                raise ValueError("Operation result does not match its operation")
        return self


class RecordedOperation(OperationModel):
    id: UUID = Field(default_factory=uuid4)
    ordinal: int = Field(gt=0)
    step: int | None = Field(default=None, ge=0)
    beat: int | None = Field(default=None, ge=0)
    payload: OperationPayload
