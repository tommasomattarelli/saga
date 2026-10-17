from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.campaign import Campaign


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")

    # Null personal profile fields inherit the instance defaults (ADR 0018).
    generation_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    generation_local_endpoint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    embedding_local_endpoint: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Encrypted AI API keys (AES-256)
    openai_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    openrouter_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Retiring the provider must not destroy existing ciphertext.
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User half of the double consent for server keys, per provider (ADR 0018 A4).
    server_key_consents: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="user", lazy="selectin", cascade="all, delete-orphan"
    )
