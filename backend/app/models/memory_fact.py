import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.document_contracts import FactMetadata
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.validated_json import ValidatedJSON


class MemoryFact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_facts"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    turn_number: Mapped[int | None] = mapped_column(Integer)
    entity_name: Mapped[str | None] = mapped_column(String(200), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(384), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    ordinal: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(20))
    assertion_type: Mapped[str | None] = mapped_column(String(20))
    fact_metadata: Mapped[FactMetadata | None] = mapped_column(ValidatedJSON(FactMetadata))
    generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    schema_version: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("id", "campaign_id", name="uq_memory_facts_id_campaign"),
        UniqueConstraint("id", "batch_id", "campaign_id", name="uq_memory_facts_batch_scope"),
        UniqueConstraint("batch_id", "ordinal", name="uq_memory_facts_batch_ordinal"),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_facts_batch",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "(batch_id IS NULL AND policy_id IS NULL AND ordinal IS NULL AND category IS NULL AND assertion_type IS NULL AND fact_metadata IS NULL AND generation_id IS NULL AND schema_version IS NULL) OR "
            "(batch_id IS NOT NULL AND policy_id IS NOT NULL AND ordinal IS NOT NULL AND ordinal > 0 AND category IS NOT NULL AND assertion_type IS NOT NULL AND fact_metadata IS NOT NULL AND generation_id IS NOT NULL AND schema_version IS NOT NULL AND schema_version = 1 AND turn_number IS NULL AND entity_name IS NULL AND entity_type IS NULL AND btrim(content) <> '')",
            name="ck_memory_facts_production_contract",
        ),
        CheckConstraint(
            "category IN ('event','information','commitment','relationship','state_change')",
            name="ck_memory_facts_category",
        ),
        CheckConstraint(
            "assertion_type IN ('occurrence','statement','belief','intention')",
            name="ck_memory_facts_assertion",
        ),
        Index("ix_memory_facts_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_memory_facts_campaign_entity", "campaign_id", "entity_name"),
    )


class MemoryFactSource(Base):
    __tablename__ = "memory_fact_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["fact_id", "batch_id", "campaign_id"],
            ["memory_facts.id", "memory_facts.batch_id", "memory_facts.campaign_id"],
            name="fk_memory_fact_sources_fact",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["batch_id", "turn_id", "campaign_id"],
            [
                "memory_batch_turns.batch_id",
                "memory_batch_turns.turn_id",
                "memory_batch_turns.campaign_id",
            ],
            name="fk_memory_fact_sources_membership",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    fact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
