import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class MemoryBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_batches"
    __table_args__ = (
        UniqueConstraint("id", "campaign_id", name="uq_memory_batches_id_campaign"),
        UniqueConstraint(
            "id", "campaign_id", "policy_id", name="uq_memory_batches_id_campaign_policy"
        ),
        ForeignKeyConstraint(
            ["policy_id", "campaign_id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_memory_batches_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["previous_batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_batches_previous",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["source_head_turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_memory_batches_source_head",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("id <> previous_batch_id", name="ck_memory_batches_not_self"),
        CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="ck_memory_batches_hash"),
        Index(
            "uq_memory_batches_input",
            "campaign_id",
            "policy_id",
            "previous_batch_id",
            "source_head_turn_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    previous_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    source_head_turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))


class MemoryBatchTurn(Base):
    __tablename__ = "memory_batch_turns"
    __table_args__ = (
        UniqueConstraint(
            "batch_id", "turn_id", "campaign_id", name="uq_memory_batch_turns_source"
        ),
        UniqueConstraint("batch_id", "turn_id", name="uq_memory_batch_turns_batch_turn"),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id"],
            ["memory_batches.id", "memory_batches.campaign_id"],
            name="fk_memory_batch_turns_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_memory_batch_turns_turn",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("ordinal > 0", name="ck_memory_batch_turns_ordinal"),
    )

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
