import uuid
from decimal import Decimal
from enum import StrEnum

from pydantic import JsonValue
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.generation_contracts import FormatMode
from app.models.base import Base, TimestampMixin, UUIDMixin


def _format_mode_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class MemoryGeneration(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_generations"
    __table_args__ = (
        UniqueConstraint(
            "id", "campaign_id", "batch_id", "policy_id", name="uq_memory_generations_document_ref"
        ),
        UniqueConstraint(
            "job_id", "role", "send_number", name="uq_memory_generations_job_role_send"
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
            "send_number IS NULL OR send_number > 0",
            name="ck_memory_generations_send_number",
        ),
        CheckConstraint(
            "(send_number IS NULL AND send_kind IS NULL AND request_identity_hash IS NULL "
            "AND format_mode IS NULL) OR "
            "(send_number IS NOT NULL AND send_kind IS NOT NULL "
            "AND request_identity_hash IS NOT NULL AND format_mode IS NOT NULL "
            "AND role <> 'batch')",
            name="ck_memory_generations_send_identity",
        ),
        CheckConstraint(
            "send_kind IS NULL OR btrim(send_kind) <> ''",
            name="ck_memory_generations_send_kind",
        ),
        CheckConstraint(
            "request_identity_hash IS NULL OR request_identity_hash ~ '^[0-9a-f]{64}$'",
            name="ck_memory_generations_request_identity_hash",
        ),
        CheckConstraint(
            "format_mode IS NULL OR format_mode IN ('strict_native', 'json_mode', 'prompt_only')",
            name="ck_memory_generations_format_mode",
        ),
        CheckConstraint(
            "status IS NULL OR btrim(status) <> ''",
            name="ck_memory_generations_status",
        ),
        CheckConstraint(
            "send_number IS NULL OR status IS NOT NULL OR "
            "(raw_candidate IS NULL AND raw_candidate_hash IS NULL AND diagnostics IS NULL "
            "AND normalization IS NULL AND input_tokens IS NULL AND output_tokens IS NULL "
            "AND cost IS NULL AND latency_ms IS NULL)",
            name="ck_memory_generations_reservation_outcome",
        ),
        CheckConstraint(
            "raw_candidate_hash IS NULL OR raw_candidate_hash ~ '^[0-9a-f]{64}$'",
            name="ck_memory_generations_candidate_hash",
        ),
        CheckConstraint(
            "raw_candidate IS NULL OR raw_candidate_hash IS NOT NULL",
            name="ck_memory_generations_candidate_hash_required",
        ),
        CheckConstraint(
            "raw_candidate IS NULL OR raw_candidate_hash = "
            "encode(sha256(convert_to(raw_candidate, 'UTF8')), 'hex')",
            name="ck_memory_generations_candidate_hash_matches",
        ),
        CheckConstraint(
            "diagnostics IS NULL OR jsonb_typeof(diagnostics) = 'array'",
            name="ck_memory_generations_diagnostics",
        ),
        CheckConstraint(
            "normalization IS NULL OR normalization IN ('none', 'json_fence_v1')",
            name="ck_memory_generations_normalization",
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
    send_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    send_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    format_mode: Mapped[FormatMode | None] = mapped_column(
        SAEnum(
            FormatMode,
            values_callable=_format_mode_values,
            native_enum=False,
            create_constraint=False,
            length=32,
        ),
        nullable=True,
    )
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_candidate: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_candidate_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnostics: Mapped[list[list[JsonValue]] | None] = mapped_column(JSONB, nullable=True)
    normalization: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
