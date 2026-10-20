"""ADR 0018 B — a campaign's versioned embedding index.

One active version and at most one open rebuild per campaign; the row snapshots
the vector-space identity (provider, model, endpoint, pipeline, observed
dimension) so a later profile or endpoint change can never silently reuse it.
"""

import hashlib
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class EmbeddingRebuildState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def text_hash(value: str) -> str:
    """Identity of the exact embedded text; a stale worker result cannot certify
    a source whose text changed in the meantime."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class EmbeddingIndex(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_indexes"
    __table_args__ = (
        UniqueConstraint("id", "campaign_id", name="uq_embedding_indexes_id_campaign"),
        Index(
            "uq_embedding_indexes_campaign_active",
            "campaign_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        Index(
            "uq_embedding_indexes_campaign_open_rebuild",
            "campaign_id",
            unique=True,
            postgresql_where=text("rebuild_state IN ('queued', 'running')"),
        ),
        CheckConstraint(
            "NOT is_active OR rebuild_state = 'completed'",
            name="ck_embedding_indexes_active_completed",
        ),
        CheckConstraint(
            "dimension IS NULL OR dimension > 0",
            name="ck_embedding_indexes_dimension_positive",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(200))
    # Operator-named alias; NULL for cloud providers. The resolved address is
    # snapshotted separately because an alias may be repointed.
    endpoint_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    endpoint_identity: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(50))
    # Observed, not requested: NULL until the provider's first real response.
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    rebuild_state: Mapped[EmbeddingRebuildState] = mapped_column(
        SAEnum(
            EmbeddingRebuildState,
            values_callable=_enum_values,
            name="embedding_rebuild_state",
        ),
        default=EmbeddingRebuildState.QUEUED,
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Worker fence: only the holder of the current token may write or cut over.
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
