"""Save model."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class Save(Base, UUIDMixin, TimestampMixin):
    """A save point for a campaign."""

    __tablename__ = "saves"
    __table_args__ = (
        ForeignKeyConstraint(
            ["continuation_id", "campaign_id"],
            ["history_continuations.id", "history_continuations.campaign_id"],
            name="fk_saves_continuation",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["head_turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_saves_head",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["memory_policy_id", "campaign_id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_saves_memory_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(memory_policy_id IS NULL AND continuation_id IS NULL AND head_turn_id IS NULL) OR "
            "(memory_policy_id IS NOT NULL AND continuation_id IS NOT NULL)",
            name="ck_saves_history_contract",
        ),
        ForeignKeyConstraint(
            ["global_checkpoint_id", "campaign_id", "memory_policy_id"],
            [
                "memory_global_checkpoints.id",
                "memory_global_checkpoints.campaign_id",
                "memory_global_checkpoints.policy_id",
            ],
            name="fk_saves_checkpoint",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["last_compacted_batch_id", "campaign_id", "memory_policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_saves_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(global_checkpoint_id IS NULL AND last_compacted_batch_id IS NULL) OR memory_policy_id IS NOT NULL",
            name="ck_saves_memory_policy",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    turn_number: Mapped[int] = mapped_column(Integer)
    scene_summary: Mapped[str] = mapped_column(Text)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)

    # Full snapshot
    campaign_snapshot: Mapped[dict] = mapped_column(JSONB)
    continuation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    head_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    memory_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    global_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    last_compacted_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="saves")
