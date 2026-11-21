from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.memory.document_contracts import FactMetadata, GlobalPayload, SummaryPayload
from app.models.memory_job import MemoryJobActivation, MemoryJobState


class _ExportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
NullableNonNegativeInt = NonNegativeInt | None


class ExportMemoryState(_ExportRow):
    id: UUID
    campaign_id: UUID
    policy_id: UUID
    context_epoch: NonNegativeInt
    global_checkpoint_id: UUID | None
    last_compacted_batch_id: UUID | None
    revision: NonNegativeInt
    created_at: datetime
    updated_at: datetime


class ExportMemoryBatch(_ExportRow):
    id: UUID
    campaign_id: UUID
    policy_id: UUID
    previous_batch_id: UUID | None
    source_head_turn_id: UUID
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    updated_at: datetime


class ExportBatchTurn(_ExportRow):
    batch_id: UUID
    ordinal: PositiveInt
    campaign_id: UUID
    turn_id: UUID


class ExportMemorySummary(_ExportRow):
    id: UUID
    campaign_id: UUID
    policy_id: UUID
    batch_id: UUID
    payload: SummaryPayload
    generation_id: UUID
    schema_version: Literal[1]
    created_at: datetime
    updated_at: datetime


class ExportGlobalCheckpoint(_ExportRow):
    id: UUID
    campaign_id: UUID
    policy_id: UUID
    batch_id: UUID
    previous_checkpoint_id: UUID | None
    payload: GlobalPayload
    generation_id: UUID
    schema_version: Literal[1]
    created_at: datetime
    updated_at: datetime


class ExportMemoryFact(_ExportRow):
    id: UUID
    campaign_id: UUID
    turn_number: NullableNonNegativeInt
    entity_name: str | None
    entity_type: str | None
    content: str
    batch_id: UUID | None
    policy_id: UUID | None
    ordinal: Annotated[StrictInt, Field(gt=0)] | None
    category: Literal["event", "information", "commitment", "relationship", "state_change"] | None
    assertion_type: Literal["occurrence", "statement", "belief", "intention"] | None
    fact_metadata: FactMetadata | None
    generation_id: UUID | None
    schema_version: Literal[1] | None
    created_at: datetime
    updated_at: datetime


class ExportFactSource(_ExportRow):
    fact_id: UUID
    turn_id: UUID
    batch_id: UUID
    campaign_id: UUID


class ExportGeneration(_ExportRow):
    id: UUID
    job_id: UUID
    attempt_id: UUID
    campaign_id: UUID
    policy_id: UUID
    batch_id: UUID
    role: Literal["batch", "summary", "facts", "global"]
    provider: str
    model: str
    input_tokens: NullableNonNegativeInt
    output_tokens: NullableNonNegativeInt
    cost: Decimal | None
    latency_ms: NullableNonNegativeInt
    created_at: datetime
    updated_at: datetime


class ExportJob(_ExportRow):
    id: UUID
    campaign_id: UUID
    policy_id: UUID
    batch_id: UUID
    memory_state_id: UUID
    context_epoch: NonNegativeInt
    kind: Literal["batch", "global"]
    previous_checkpoint_id: UUID | None
    source_turn_ids: list[UUID]
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    instruction_version: str = Field(min_length=1)
    language: str
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_version: str
    prompt_version: str
    state: MemoryJobState
    attempt_count: NonNegativeInt
    retry_cycle: NonNegativeInt
    cycle_attempt_count: NonNegativeInt
    last_error: str | None
    activation_state: MemoryJobActivation
    created_at: datetime
    updated_at: datetime


class ExportJobAttempt(_ExportRow):
    id: UUID
    job_id: UUID
    campaign_id: UUID
    attempt_number: PositiveInt
    retry_cycle: NonNegativeInt
    state: Literal["started", "succeeded", "failed", "uncertain"]
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime
