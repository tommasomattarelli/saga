"""Campaign template model."""

from sqlalchemy import String, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


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

    # Template content
    content: Mapped[dict] = mapped_column(JSONB)
