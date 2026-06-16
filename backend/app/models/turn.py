import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Turn(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "turns"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer)

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

    # Compressed summary for memory
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summarization_failed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Vector embedding for semantic search
    embedding: Mapped[list | None] = mapped_column(Vector(384), nullable=True)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="turns")  # noqa: F821
