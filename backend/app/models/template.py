"""Campaign template model."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Template(Base, UUIDMixin, TimestampMixin):
    """Campaign template stored in the database."""

    __tablename__ = "templates"

    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(20))
    difficulty: Mapped[int] = mapped_column(Integer, default=5)
    tags: Mapped[list] = mapped_column(JSONB, default=list)

    # Persona preset — drives DM tone (grimdark|heroic|dark_fantasy|horror)
    persona_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Free-form XML override; if set, wins over persona_preset
    persona_xml: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Template content
    content: Mapped[dict] = mapped_column(JSONB)
