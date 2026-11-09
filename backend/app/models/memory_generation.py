import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class MemoryGeneration(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_generations"
    __table_args__ = (
        UniqueConstraint(
            "id", "campaign_id", "batch_id", "policy_id", name="uq_memory_generations_document_ref"
        ),
        ForeignKeyConstraint(
            ["job_id", "campaign_id", "policy_id", "batch_id"],
            [
                "memory_jobs.id",
                "memory_jobs.campaign_id",
                "memory_jobs.policy_id",
                "memory_jobs.batch_id",
            ],
            name="fk_memory_generations_job_provenance",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["attempt_id", "job_id", "campaign_id"],
            [
                "memory_job_attempts.id",
                "memory_job_attempts.job_id",
                "memory_job_attempts.campaign_id",
            ],
            name="fk_memory_generations_attempt_provenance",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["policy_id", "campaign_id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_memory_generations_policy_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_generations_batch_campaign_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "role IN ('batch', 'summary', 'facts', 'global')", name="ck_memory_generations_role"
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="ck_memory_generations_input_tokens"
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_memory_generations_output_tokens",
        ),
        CheckConstraint("cost IS NULL OR cost >= 0", name="ck_memory_generations_cost"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="ck_memory_generations_latency"
        ),
        Index("ix_memory_generations_campaign_id", "campaign_id"),
        Index("ix_memory_generations_job_scope", "job_id", "campaign_id", "policy_id", "batch_id"),
        Index("ix_memory_generations_attempt_scope", "attempt_id", "job_id", "campaign_id"),
        Index("ix_memory_generations_policy_scope", "policy_id", "campaign_id"),
        Index("ix_memory_generations_batch_scope", "batch_id", "campaign_id", "policy_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
