from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.save import Save
    from app.models.turn import Turn
    from app.models.user import User


class CampaignStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class DeathMode(StrEnum):
    IRONMAN = "ironman"
    DESTINO = "destino"
    CRONISTA = "cronista"


class Campaign(Base, UUIDMixin, TimestampMixin):
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

    # Rolling story summary — updated every N turns (see gameplay.global_summary_update_every)
    global_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Persona preset — copied from template at creation, drives DM narrative tone
    persona_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    persona_xml: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="campaigns")
    turns: Mapped[list[Turn]] = relationship(
        back_populates="campaign", lazy="selectin", cascade="all, delete-orphan"
    )
    saves: Mapped[list[Save]] = relationship(
        back_populates="campaign", lazy="selectin", cascade="all, delete-orphan"
    )
