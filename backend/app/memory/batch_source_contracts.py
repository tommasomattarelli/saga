import hashlib
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.memory.operation_contracts import OperationOrigin, OperationOutcome, StateDelta
from app.memory.operation_results import (
    AttackResult,
    CheckResult,
    DeathResult,
    ErrorResult,
    MessageResult,
    OperationModel,
)


class NPCSourceResult(OperationModel):
    kind: Literal["npc"] = "npc"
    npc_id: str
    status: Literal["speaking", "silent", "failed", "created"]
    action: str | None
    axis_changes: dict[str, int]


SourceResult = Annotated[
    MessageResult | ErrorResult | AttackResult | CheckResult | DeathResult | NPCSourceResult,
    Field(discriminator="kind"),
]


class SourceOperationPayload(OperationModel):
    origin: OperationOrigin
    name: str
    outcome: OperationOutcome
    arguments: dict[str, JsonValue]
    result: SourceResult
    deltas: tuple[StateDelta, ...]


class SourceOperation(OperationModel):
    id: UUID
    ordinal: int = Field(gt=0)
    step: int | None
    beat: int | None
    payload: SourceOperationPayload


class BatchTurnSource(OperationModel):
    reference: str = Field(pattern=r"^t[1-9][0-9]*$")
    turn_id: UUID
    player_action: str
    narration: str
    operations: tuple[SourceOperation, ...] | None


class BatchInput(OperationModel):
    schema_version: Literal[1] = 1
    turns: tuple[BatchTurnSource, ...] = Field(min_length=1)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def source_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
