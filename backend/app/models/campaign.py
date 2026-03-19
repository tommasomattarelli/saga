"""Campaign model."""

import uuid
from enum import StrEnum

from sqlalchemy import String, Integer, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class CampaignStatus(StrEnum):
    """Campaign lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class DeathMode(StrEnum):
    """Player death handling mode."""

    IRONMAN = "ironman"
    DESTINO = "destino"
    CRONISTA = "cronista"


class Campaign(Base, UUIDMixin, TimestampMixin):
    """A single campaign / playthrough."""

    __tablename__ = "campaigns"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    template_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[CampaignStatus] = mapped_column(
        SAEnum(CampaignStatus), default=CampaignStatus.ACTIVE
    )
    death_mode: Mapped[DeathMode] = mapped_column(SAEnum(DeathMode))
    turn_number: Mapped[int] = mapped_column(Integer, default=0)

    # Character data (denormalized for fast access)
    character_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # World state snapshot (companions, factions, locations, time, weather)
    world_state: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Active quests
    quests: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="campaigns")  # noqa: F821
    turns: Mapped[list["Turn"]] = relationship(back_populates="campaign", lazy="selectin")  # noqa: F821
    saves: Mapped[list["Save"]] = relationship(back_populates="campaign", lazy="selectin")  # noqa: F821
