"""Turn model - represents a single game turn."""

import uuid

from sqlalchemy import Integer, Text, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import Base, UUIDMixin, TimestampMixin


class Turn(Base, UUIDMixin, TimestampMixin):
    """A single game turn with player action and DM response."""

    __tablename__ = "turns"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    turn_number: Mapped[int] = mapped_column(Integer)

    # Player input
    player_action: Mapped[str] = mapped_column(Text)

    # DM structured output
    narration: Mapped[str] = mapped_column(Text)
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

    # Vector embedding for semantic search
    embedding: Mapped[list | None] = mapped_column(Vector(384), nullable=True)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="turns")  # noqa: F821
