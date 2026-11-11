from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, field_validator

from app.memory.operation_contracts import OperationPayload
from app.models.campaign import CampaignStatus, Difficulty
from app.schemas.campaign_export_history import (
    ExportContinuation,
    ExportMemoryPolicy,
    ExportSave,
)
from app.schemas.campaign_export_memory import (
    ExportBatchTurn,
    ExportFactSource,
    ExportGeneration,
    ExportGlobalCheckpoint,
    ExportJob,
    ExportJobAttempt,
    ExportMemoryBatch,
    ExportMemoryFact,
    ExportMemoryState,
    ExportMemorySummary,
)


class _ExportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
NullableNonNegativeInt = NonNegativeInt | None


class ExportCampaign(_ExportRow):
    id: UUID
    world_slug: str
    world_version: str | None
    name: str
    language: str
    status: CampaignStatus
    difficulty: Difficulty
    turn_number: NonNegativeInt
    memory_policy_id: UUID | None
    active_continuation_id: UUID | None
    active_head_turn_id: UUID | None
    active_memory_state_id: UUID | None
    context_epoch: NonNegativeInt
    fork_on_next_action: bool
    character_data: dict[str, JsonValue]
    world_baseline: dict[str, JsonValue] | None
    world_state: dict[str, JsonValue]
    quests: dict[str, JsonValue]
    global_summary: str | None
    persona_preset: str | None
    persona_xml: str | None
    created_at: datetime
    updated_at: datetime


class ExportTurn(_ExportRow):
    id: UUID
    campaign_id: UUID
    turn_number: NonNegativeInt
    continuation_id: UUID | None
    parent_turn_id: UUID | None
    history_depth: NullableNonNegativeInt
    parent_depth: NullableNonNegativeInt
    operations_version: Literal[1] | None
    operation_count: NullableNonNegativeInt
    player_action: str
    narration: str
    narration_segments: list[JsonValue] | None
    dice_rolls: dict[str, JsonValue] | None
    companion_actions: dict[str, JsonValue] | None
    world_updates: dict[str, JsonValue] | None
    scene_mood: str | None
    suggested_actions: list[JsonValue] | None
    model_used: str
    importance_score: StrictInt
    summary: str | None
    summarization_failed: bool
    created_at: datetime
    updated_at: datetime


class ExportTurnOperation(_ExportRow):
    id: UUID
    campaign_id: UUID
    turn_id: UUID
    ordinal: Annotated[StrictInt, Field(gt=0)]
    step: NullableNonNegativeInt
    beat: NullableNonNegativeInt
    payload: OperationPayload
    created_at: datetime
    updated_at: datetime


class CampaignExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1]
    exported_at: datetime
    campaign: ExportCampaign
    turns: list[ExportTurn]
    turn_operations: list[ExportTurnOperation]
    continuations: list[ExportContinuation]
    saves: list[ExportSave]
    memory_policies: list[ExportMemoryPolicy]
    memory_states: list[ExportMemoryState]
    memory_batches: list[ExportMemoryBatch]
    batch_turns: list[ExportBatchTurn]
    memory_summaries: list[ExportMemorySummary]
    global_checkpoints: list[ExportGlobalCheckpoint]
    memory_facts: list[ExportMemoryFact]
    fact_sources: list[ExportFactSource]
    generations: list[ExportGeneration]
    jobs: list[ExportJob]
    job_attempts: list[ExportJobAttempt]

    @field_validator("format_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("format_version must be an integer")
        return value
