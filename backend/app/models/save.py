"""Save model."""

import uuid

from sqlalchemy import Integer, String, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class Save(Base, UUIDMixin, TimestampMixin):
    """A save point for a campaign."""

    __tablename__ = "saves"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    turn_number: Mapped[int] = mapped_column(Integer)
    scene_summary: Mapped[str] = mapped_column(Text)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)

    # Full snapshot
    campaign_snapshot: Mapped[dict] = mapped_column(JSONB)

    # Relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="saves")  # noqa: F821
