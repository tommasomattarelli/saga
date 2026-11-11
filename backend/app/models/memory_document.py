import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.document_contracts import GlobalPayload, SummaryPayload
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.validated_json import ValidatedJSON


class MemorySummary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_summaries"
    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_memory_summaries_batch"),
        CheckConstraint("schema_version = 1", name="ck_memory_summaries_schema_version"),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_summaries_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["generation_id", "campaign_id", "batch_id", "policy_id"],
            [
                "memory_generations.id",
                "memory_generations.campaign_id",
                "memory_generations.batch_id",
                "memory_generations.policy_id",
            ],
            name="fk_memory_summaries_generation",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND payload ? 'text' AND payload - 'text' = '{}'::jsonb AND jsonb_typeof(payload->'text')='string' AND btrim(payload->>'text') <> ''",
            name="ck_memory_summaries_payload",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[SummaryPayload] = mapped_column(ValidatedJSON(SummaryPayload))
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class MemoryGlobalCheckpoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_global_checkpoints"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="ck_memory_global_checkpoints_schema_version"),
        UniqueConstraint(
            "id", "campaign_id", "policy_id", name="uq_memory_global_checkpoints_scope"
        ),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_global_checkpoints_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["previous_checkpoint_id", "campaign_id", "policy_id"],
            [
                "memory_global_checkpoints.id",
                "memory_global_checkpoints.campaign_id",
                "memory_global_checkpoints.policy_id",
            ],
            name="fk_memory_global_checkpoints_previous",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["generation_id", "campaign_id", "batch_id", "policy_id"],
            [
                "memory_generations.id",
                "memory_generations.campaign_id",
                "memory_generations.batch_id",
                "memory_generations.policy_id",
            ],
            name="fk_memory_global_checkpoints_generation",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint(
            "id <> previous_checkpoint_id", name="ck_memory_global_checkpoints_not_self"
        ),
        Index(
            "uq_memory_global_checkpoints_transition",
            "campaign_id",
            "policy_id",
            "previous_checkpoint_id",
            "batch_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    previous_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    payload: Mapped[GlobalPayload] = mapped_column(ValidatedJSON(GlobalPayload))
    generation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class MemoryState(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_states"
    __table_args__ = (
        UniqueConstraint("id", "campaign_id", "policy_id", name="uq_memory_states_scope"),
        ForeignKeyConstraint(
            ["policy_id", "campaign_id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_memory_states_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["global_checkpoint_id", "campaign_id", "policy_id"],
            [
                "memory_global_checkpoints.id",
                "memory_global_checkpoints.campaign_id",
                "memory_global_checkpoints.policy_id",
            ],
            name="fk_memory_states_checkpoint",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["last_compacted_batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_states_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("context_epoch >= 0 AND revision >= 0", name="ck_memory_states_counters"),
        CheckConstraint(
            "global_checkpoint_id IS NULL OR last_compacted_batch_id IS NOT NULL",
            name="ck_memory_states_checkpoint_has_batch",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    context_epoch: Mapped[int] = mapped_column(Integer)
    global_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    last_compacted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
