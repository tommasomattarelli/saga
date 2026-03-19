"""User model."""

import uuid

from sqlalchemy import String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class User(Base, UUIDMixin, TimestampMixin):
    """User account."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")

    # Encrypted AI API keys (AES-256)
    openai_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="user", lazy="selectin")  # noqa: F821
