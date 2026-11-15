import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.memory.job_contracts import MemoryJobExecutionIdentity, MemoryJobManifest
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.validated_json import ValidatedJSON


class MemoryJobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    BLOCKED = "blocked"
    MANUAL_RETRY_REQUIRED = "manual_retry_required"
    EXHAUSTED = "exhausted"
    SUCCEEDED = "succeeded"


class MemoryJobTerminalReason(StrEnum):
    REQUIRED_RESULT_SEND_BUDGET_EXHAUSTED = "required_result_send_budget_exhausted"


def _terminal_reason_values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class MemoryJobActivation(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DETACHED = "detached"


class MemoryJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_jobs"
    __table_args__ = (
        UniqueConstraint("campaign_id", "logical_key", name="uq_memory_jobs_campaign_key"),
        UniqueConstraint("id", "campaign_id", name="uq_memory_jobs_id_campaign"),
        UniqueConstraint(
            "id", "campaign_id", "policy_id", "batch_id", name="uq_memory_jobs_provenance"
        ),
        ForeignKeyConstraint(
            ["policy_id", "campaign_id"],
            ["memory_policies.id", "memory_policies.campaign_id"],
            name="fk_memory_jobs_policy_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["batch_id", "campaign_id", "policy_id"],
            ["memory_batches.id", "memory_batches.campaign_id", "memory_batches.policy_id"],
            name="fk_memory_jobs_batch_campaign_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["memory_state_id", "campaign_id", "policy_id"],
            ["memory_states.id", "memory_states.campaign_id", "memory_states.policy_id"],
            name="fk_memory_jobs_state_campaign_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["previous_checkpoint_id", "campaign_id", "policy_id"],
            [
                "memory_global_checkpoints.id",
                "memory_global_checkpoints.campaign_id",
                "memory_global_checkpoints.policy_id",
            ],
            name="fk_memory_jobs_checkpoint_campaign_policy",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("kind IN ('batch', 'global')", name="ck_memory_jobs_kind"),
        CheckConstraint(
            "state IN ('queued', 'running', 'retry_wait', 'blocked', 'manual_retry_required', "
            "'exhausted', 'succeeded')",
            name="ck_memory_jobs_state",
        ),
        CheckConstraint(
            "(execution_identity IS NULL AND execution_identity_hash IS NULL "
            "AND execution_identity_version IS NULL) OR "
            "(execution_identity IS NOT NULL AND jsonb_typeof(execution_identity) = 'object' "
            "AND execution_identity_hash IS NOT NULL "
            "AND execution_identity_hash ~ '^[0-9a-f]{64}$' "
            "AND execution_identity_version IS NOT NULL AND execution_identity_version > 0 "
            "AND jsonb_typeof(execution_identity->'result_identities') = 'object' "
            "AND execution_identity->'max_sends_per_result' IS NOT NULL "
            "AND jsonb_typeof(execution_identity->'max_sends_per_result') = 'number' "
            "AND execution_identity->>'max_sends_per_result' IS NOT NULL "
            "AND execution_identity->>'max_sends_per_result' ~ '^[1-9][0-9]*$' "
            "AND execution_identity->'result_identities' <> '{}'::jsonb)",
            name="ck_memory_jobs_execution_identity",
        ),
        CheckConstraint(
            "execution_contract_version IS NULL OR execution_contract_version = 1",
            name="ck_memory_jobs_execution_contract_version",
        ),
        CheckConstraint(
            "execution_contract_version IS NULL OR execution_identity IS NOT NULL "
            "OR state = 'blocked'",
            name="ck_memory_jobs_marked_identity_state",
        ),
        CheckConstraint(
            "terminal_at IS NULL OR state IN ('succeeded', 'exhausted')",
            name="ck_memory_jobs_terminal_state",
        ),
        CheckConstraint(
            "terminal_reason IS NULL OR "
            "(state = 'exhausted' AND terminal_reason = "
            "'required_result_send_budget_exhausted')",
            name="ck_memory_jobs_terminal_reason",
        ),
        CheckConstraint(
            "execution_identity IS NOT NULL OR terminal_at IS NULL",
            name="ck_memory_jobs_terminal_identity",
        ),
        CheckConstraint(
            "execution_identity IS NULL OR "
            "((state IN ('succeeded', 'exhausted')) = (terminal_at IS NOT NULL))",
            name="ck_memory_jobs_terminal_time",
        ),
        CheckConstraint(
            "activation_state IN ('pending', 'active', 'detached')",
            name="ck_memory_jobs_activation",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND retry_cycle >= 0 AND cycle_attempt_count >= 0 "
            "AND cycle_attempt_count <= attempt_count",
            name="ck_memory_jobs_counters",
        ),
        CheckConstraint("context_epoch >= 0", name="ck_memory_jobs_context_epoch"),
        CheckConstraint("logical_key ~ '^[0-9a-f]{64}$'", name="ck_memory_jobs_logical_key"),
        CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="ck_memory_jobs_manifest_hash"),
        CheckConstraint(
            "kind <> 'batch' OR previous_checkpoint_id IS NULL",
            name="ck_memory_jobs_batch_predecessor",
        ),
        CheckConstraint(
            "(state = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)"
            " OR (state <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_memory_jobs_claim_state",
        ),
        Index("ix_memory_jobs_policy_campaign", "policy_id", "campaign_id"),
        Index("ix_memory_jobs_batch_scope", "batch_id", "campaign_id", "policy_id"),
        Index("ix_memory_jobs_state_scope", "memory_state_id", "campaign_id", "policy_id"),
        Index(
            "ix_memory_jobs_checkpoint_scope",
            "previous_checkpoint_id",
            "campaign_id",
            "policy_id",
        ),
        Index("ix_memory_jobs_campaign_id", "campaign_id"),
        Index("ix_memory_jobs_due", "state", "next_attempt_at"),
        Index(
            "uq_memory_jobs_input",
            "campaign_id",
            "policy_id",
            "batch_id",
            "kind",
            "previous_checkpoint_id",
            "manifest_hash",
            "producer_version",
            "prompt_version",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    memory_state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    context_epoch: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    previous_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    logical_key: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[MemoryJobManifest] = mapped_column(ValidatedJSON(MemoryJobManifest))
    execution_identity: Mapped[MemoryJobExecutionIdentity | None] = mapped_column(
        ValidatedJSON(MemoryJobExecutionIdentity), nullable=True
    )
    execution_identity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_identity_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    producer_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(32))
    attempt_count: Mapped[int] = mapped_column(Integer)
    retry_cycle: Mapped[int] = mapped_column(Integer)
    cycle_attempt_count: Mapped[int] = mapped_column(Integer)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    activation_state: Mapped[str] = mapped_column(String(16))
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_reason: Mapped[MemoryJobTerminalReason | None] = mapped_column(
        SAEnum(
            MemoryJobTerminalReason,
            values_callable=_terminal_reason_values,
            native_enum=False,
            create_constraint=False,
            length=64,
        ),
        nullable=True,
    )


@event.listens_for(Session, "before_flush")
def verify_execution_identity_hashes(
    session: Session, _flush_context: object, _instances: object
) -> None:
    for job in session.new.union(session.dirty):
        if isinstance(job, MemoryJob) and job.execution_identity is not None:
            if job.execution_identity_hash is None or job.execution_identity_version is None:
                raise ValueError("Memory job execution identity metadata is incomplete.")
            job.execution_identity.verify(
                job.execution_identity_version, job.execution_identity_hash
            )


class MemoryJobAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_job_attempts"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "campaign_id", "attempt_number", name="uq_memory_job_attempts_number"
        ),
        UniqueConstraint("id", "campaign_id", name="uq_memory_job_attempts_id_campaign"),
        UniqueConstraint("id", "job_id", "campaign_id", name="uq_memory_job_attempts_provenance"),
        ForeignKeyConstraint(
            ["job_id", "campaign_id"],
            ["memory_jobs.id", "memory_jobs.campaign_id"],
            name="fk_memory_job_attempts_job_campaign",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "attempt_number > 0 AND retry_cycle >= 0", name="ck_memory_job_attempts_counts"
        ),
        CheckConstraint(
            "state IN ('started', 'succeeded', 'failed', 'uncertain')",
            name="ck_memory_job_attempts_state",
        ),
        Index("ix_memory_job_attempts_campaign_id", "campaign_id"),
        Index("ix_memory_job_attempts_job_campaign", "job_id", "campaign_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE")
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    retry_cycle: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16))
    claim_token: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
