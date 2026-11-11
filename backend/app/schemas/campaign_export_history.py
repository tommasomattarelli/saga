from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from app.memory.production_policy import MemoryProductionPolicy


class _ExportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class ExportContinuation(_ExportRow):
    id: UUID
    campaign_id: UUID
    parent_continuation_id: UUID | None
    fork_head_turn_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ExportSave(_ExportRow):
    id: UUID
    campaign_id: UUID
    name: str
    turn_number: NonNegativeInt
    scene_summary: str
    is_auto: bool
    campaign_snapshot: dict[str, JsonValue]
    continuation_id: UUID | None
    head_turn_id: UUID | None
    memory_policy_id: UUID | None
    global_checkpoint_id: UUID | None
    last_compacted_batch_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ExportMemoryPolicy(_ExportRow):
    id: UUID
    campaign_id: UUID
    schema_version: Literal[1]
    payload: MemoryProductionPolicy
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    updated_at: datetime
