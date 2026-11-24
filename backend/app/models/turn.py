import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class Turn(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "turns"
    # Composite target so a source_embeddings row can bind (turn, campaign)
    # atomically and reject cross-campaign links (ADR 0018 B3).
    __table_args__ = (
        UniqueConstraint("id", "campaign_id", name="uq_turns_id_campaign"),
        UniqueConstraint("id", "campaign_id", "history_depth", name="uq_turns_id_campaign_depth"),
        CheckConstraint(
            "(operations_version IS NULL AND operation_count IS NULL) OR "
            "(operations_version IS NOT NULL AND operations_version=1 AND "
            "operation_count IS NOT NULL AND operation_count >= 0)",
            name="ck_turns_operations_contract",
        ),
        ForeignKeyConstraint(
            ["continuation_id", "campaign_id"],
            ["history_continuations.id", "history_continuations.campaign_id"],
            name="fk_turns_continuation",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["parent_turn_id", "campaign_id", "parent_depth"],
            ["turns.id", "turns.campaign_id", "turns.history_depth"],
            name="fk_turns_parent_depth",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(continuation_id IS NULL AND parent_turn_id IS NULL AND history_depth IS NULL) OR "
            "(continuation_id IS NOT NULL AND history_depth IS NOT NULL AND "
            "((parent_turn_id IS NULL AND history_depth=1) OR (parent_turn_id IS NOT NULL AND history_depth>1)))",
            name="ck_turns_history_contract",
        ),
        Index(
            "uq_turns_continuation_parent",
            "continuation_id",
            "parent_turn_id",
            unique=True,
            postgresql_where=text("continuation_id IS NOT NULL"),
            postgresql_nulls_not_distinct=True,
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer)
    continuation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    history_depth: Mapped[int | None] = mapped_column(Integer)
    operations_version: Mapped[int | None] = mapped_column(Integer)
    operation_count: Mapped[int | None] = mapped_column(Integer)
    parent_depth: Mapped[int | None] = mapped_column(
        Integer, Computed("history_depth - 1", persisted=True)
    )

    # Player input
    player_action: Mapped[str] = mapped_column(Text)

    # DM structured output
    narration: Mapped[str] = mapped_column(Text)
    narration_segments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    dice_rolls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    companion_actions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    world_updates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scene_mood: Mapped[str | None] = mapped_column(String(50), nullable=True)
    suggested_actions: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # AI metadata
    model_used: Mapped[str] = mapped_column(String(50))
    importance_score: Mapped[int] = mapped_column(Integer, default=5)

    # Retained for historical exports, not the current memory pipeline.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarization_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Historical vectors; active recall uses the versioned source index.
    embedding: Mapped[list | None] = mapped_column(Vector(384), nullable=True)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="turns", foreign_keys=[campaign_id])
