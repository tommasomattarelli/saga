"""ADR 0018 B — a source text's embedding under one index version.

Pending rows are the rebuild queue: no separate job table. The composite foreign
keys bind the source, its campaign and the index together, so a source from one
campaign can never be linked to another campaign's index.
"""

import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class EmbeddingSourceType(StrEnum):
    TURN = "turn"
    MEMORY_FACT = "memory_fact"


class EmbeddingWorkState(StrEnum):
    PENDING = "pending"
    EMBEDDED = "embedded"
    FAILED = "failed"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class SourceEmbedding(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "source_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["index_id", "campaign_id"],
            ["embedding_indexes.id", "embedding_indexes.campaign_id"],
            name="fk_source_embeddings_index_campaign",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["turn_id", "campaign_id"],
            ["turns.id", "turns.campaign_id"],
            name="fk_source_embeddings_turn_campaign",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["memory_fact_id", "campaign_id"],
            ["memory_facts.id", "memory_facts.campaign_id"],
            name="fk_source_embeddings_memory_fact_campaign",
            ondelete="CASCADE",
        ),
        Index(
            "uq_source_embeddings_index_turn",
            "index_id",
            "turn_id",
            unique=True,
            postgresql_where=text("turn_id IS NOT NULL"),
        ),
        Index(
            "uq_source_embeddings_index_memory_fact",
            "index_id",
            "memory_fact_id",
            unique=True,
            postgresql_where=text("memory_fact_id IS NOT NULL"),
        ),
        CheckConstraint(
            "num_nonnulls(turn_id, memory_fact_id) = 1",
            name="ck_source_embeddings_single_source",
        ),
        CheckConstraint(
            "(source_type = 'turn' AND turn_id IS NOT NULL)"
            " OR (source_type = 'memory_fact' AND memory_fact_id IS NOT NULL)",
            name="ck_source_embeddings_kind_matches_reference",
        ),
        CheckConstraint(
            "work_state <> 'embedded' OR embedding IS NOT NULL",
            name="ck_source_embeddings_embedded_has_vector",
        ),
        Index("ix_source_embeddings_index_work_state", "index_id", "work_state"),
    )

    index_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    source_type: Mapped[EmbeddingSourceType] = mapped_column(
        SAEnum(EmbeddingSourceType, values_callable=_enum_values, name="embedding_source_type")
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    memory_fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # sha256 of the exact Turn.summary / MemoryFact.content that was embedded.
    text_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list | None] = mapped_column(Vector(), nullable=True)
    work_state: Mapped[EmbeddingWorkState] = mapped_column(
        SAEnum(EmbeddingWorkState, values_callable=_enum_values, name="embedding_work_state"),
        default=EmbeddingWorkState.PENDING,
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
