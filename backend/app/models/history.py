import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.production_policy import MemoryProductionPolicy
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.validated_json import ValidatedJSON


class MemoryPolicy(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_policies"
    __table_args__ = (
        UniqueConstraint("campaign_id", name="uq_memory_policies_campaign_snapshot"),
        UniqueConstraint("id", "campaign_id", name="uq_memory_policies_id_campaign"),
        CheckConstraint("schema_version = 1", name="ck_memory_policies_schema_version"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_memory_policies_hash"),
        CheckConstraint(
            "payload ? 'batch_turns' AND jsonb_typeof(payload->'batch_turns') = 'number' AND (payload->>'batch_turns')::integer > 0",
            name="ck_memory_policies_batch_size",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[MemoryProductionPolicy] = mapped_column(ValidatedJSON(MemoryProductionPolicy))
    payload_hash: Mapped[str] = mapped_column(String(64))


class HistoryContinuation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "history_continuations"
    __table_args__ = (
        UniqueConstraint("id", "campaign_id", name="uq_history_continuations_id_campaign"),
        ForeignKeyConstraint(
            ["parent_continuation_id", "campaign_id"],
            ["history_continuations.id", "history_continuations.campaign_id"],
            name="fk_history_continuations_parent",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["fork_head_turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_history_continuations_fork",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "parent_continuation_id IS NOT NULL OR fork_head_turn_id IS NULL",
            name="ck_history_continuations_root",
        ),
        CheckConstraint("id <> parent_continuation_id", name="ck_history_continuations_not_self"),
        Index(
            "uq_history_continuations_root",
            "campaign_id",
            unique=True,
            postgresql_where=text("parent_continuation_id IS NULL"),
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
    )
    parent_continuation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    fork_head_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
