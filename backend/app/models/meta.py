"""Meta models: achievements and profile stats."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Achievement(Base, UUIDMixin, TimestampMixin):
    """Player achievement."""

    __tablename__ = "achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)


class ProfileStats(Base, UUIDMixin, TimestampMixin):
    """Aggregate stats for a user profile."""

    __tablename__ = "profile_stats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True
    )
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    total_campaigns: Mapped[int] = mapped_column(Integer, default=0)
    total_play_time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    stats_data: Mapped[dict] = mapped_column(JSONB, default=dict)
