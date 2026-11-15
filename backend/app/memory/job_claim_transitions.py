import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.generation_execution_ledger import GenerationOutcomeStatus, GenerationSendKind
from app.memory.generation_receipts import decode_receipt
from app.memory.job_contracts import (
    MemoryGenerationRequestIdentitySnapshot,
    MemoryJobExecutionIdentity,
)
from app.memory.production_policy import JobsPolicy
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt, MemoryJobTerminalReason

INCOMPATIBLE_JOB_REASON = "This memory job's saved contract or source is incompatible."
UNSUPPORTED_HISTORY_REASON = "Stored memory generation history is unsupported."
UNSUPPORTED_IDENTITY_REASON = "This memory job has no supported execution identity."
CANNOT_BIND_IDENTITY_REASON = "This memory job cannot bind an execution identity."
INTEGRITY_BLOCK_REASONS = frozenset(
    {
        INCOMPATIBLE_JOB_REASON,
        UNSUPPORTED_HISTORY_REASON,
        UNSUPPORTED_IDENTITY_REASON,
        CANNOT_BIND_IDENTITY_REASON,
    }
)


def is_integrity_block_reason(reason: str | None) -> bool:
    return reason in INTEGRITY_BLOCK_REASONS


@dataclass(frozen=True)
class RoleSendState:
    send_count: int
    reusable_candidate: bool


def inspect_role_sends(
    generations: tuple[MemoryGeneration, ...],
    required_roles: tuple[str, ...],
    identity: MemoryJobExecutionIdentity,
) -> dict[str, RoleSendState] | None:
    counts = {role: 0 for role in required_roles}
    reusable = {role: False for role in required_roles}
    if set(identity.result_identities) != set(required_roles):
        return None
    for generation in generations:
        if (
            generation.role not in counts
            or generation.send_number != counts[generation.role] + 1
            or generation.send_kind is None
            or generation.request_identity_hash is None
            or generation.request_identity_snapshot is None
            or generation.format_mode is None
        ):
            return None
        try:
            send_kind = GenerationSendKind(generation.send_kind)
            request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
                generation.request_identity_snapshot
            )
        except (PydanticValidationError, ValueError):
            return None
        frozen = identity.result_identities[generation.role]
        if (
            request.digest != generation.request_identity_hash
            or request.snapshot_json != generation.request_identity_snapshot
            or request.model_dump(mode="json", exclude={"initial_prefix_hash", "format_mode"})
            != frozen.model_dump(
                mode="json",
                exclude={"request_identity_hash", "initial_prefix_hash", "format_mode"},
            )
            or request.format_mode != generation.format_mode
            or generation.provider != frozen.provider
            or generation.model != frozen.model
            or (
                send_kind is GenerationSendKind.INITIAL
                and (
                    request.digest != frozen.request_identity_hash
                    or request.format_mode != frozen.format_mode
                )
            )
            or (
                send_kind is not GenerationSendKind.INITIAL
                and request.format_mode != frozen.format_mode
                and not (
                    request.format_mode.value == "json_mode"
                    and frozen.allow_json_mode_fallback
                    or request.format_mode.value == "prompt_only"
                    and frozen.allow_prompt_only_fallback
                )
            )
            or (counts[generation.role] == 0) != (send_kind is GenerationSendKind.INITIAL)
        ):
            return None
        counts[generation.role] += 1
        if (generation.raw_candidate is None and generation.raw_candidate_hash is not None) or (
            generation.raw_candidate is not None
            and generation.raw_candidate_hash
            != hashlib.sha256(generation.raw_candidate.encode()).hexdigest()
        ):
            return None
        receipt = None
        if generation.receipt is not None:
            try:
                receipt = decode_receipt(generation.receipt, generation.raw_candidate)
            except ValueError:
                return None
        if generation.status is None:
            if any(
                value is not None
                for value in (
                    generation.receipt,
                    generation.raw_candidate,
                    generation.raw_candidate_hash,
                    generation.outcome_reason,
                    generation.diagnostics,
                    generation.normalization,
                    generation.input_tokens,
                    generation.output_tokens,
                    generation.cost,
                    generation.latency_ms,
                )
            ):
                return None
            continue
        try:
            status = GenerationOutcomeStatus(generation.status)
        except ValueError:
            return None
        if status is GenerationOutcomeStatus.VALID:
            if (
                receipt is None
                or receipt.text is None
                or generation.raw_candidate is None
                or generation.outcome_reason is not None
                or receipt.refusal is not None
                or receipt.blocked_reason is not None
            ):
                return None
            reusable[generation.role] = True
    return {role: RoleSendState(counts[role], reusable[role]) for role in required_roles}


async def fail_claim_transition(
    db: AsyncSession,
    job: MemoryJob,
    attempt: MemoryJobAttempt,
    policy: JobsPolicy,
    now: datetime,
    *,
    uncertain: bool = False,
    configuration_required: bool = False,
    blocked_reason: str | None = None,
) -> None:
    reason = (
        "Memory generation requires a configuration update."
        if configuration_required
        else blocked_reason
        if blocked_reason is not None
        else "Memory generation was interrupted."
        if uncertain
        else "Memory generation did not produce a valid result."
    )
    attempt.state = "uncertain" if uncertain else "failed"
    attempt.finished_at, attempt.error = now, reason
    job.state = "blocked"
    job.claim_token, job.lease_expires_at = None, None
    job.last_error, job.next_attempt_at = reason, None

    if configuration_required or blocked_reason is not None:
        job.state = "blocked"
    elif job.cycle_attempt_count >= policy.max_attempts:
        await apply_claim_limit_transition(db, job, now)
    else:
        job.state = "retry_wait"
        job.next_attempt_at = now + timedelta(
            seconds=policy.retry_backoff_seconds[job.cycle_attempt_count - 1]
        )


async def apply_claim_limit_transition(db: AsyncSession, job: MemoryJob, now: datetime) -> None:
    identity = job.execution_identity
    if identity is None:
        job.state = "blocked"
        job.last_error = UNSUPPORTED_IDENTITY_REASON
        return

    roles = ("summary", "facts") if job.kind == "batch" else ("global",)
    generations = tuple(
        await db.scalars(
            select(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
            .order_by(MemoryGeneration.role, MemoryGeneration.send_number)
        )
    )
    role_sends = inspect_role_sends(generations, roles, identity)
    if role_sends is None:
        job.state = "blocked"
        job.last_error = UNSUPPORTED_HISTORY_REASON
        return

    exhausted = any(
        not role_sends[role].reusable_candidate
        and role_sends[role].send_count >= identity.max_sends_per_result
        for role in roles
    )
    if exhausted:
        job.state = "exhausted"
        job.terminal_reason = MemoryJobTerminalReason.REQUIRED_RESULT_SEND_BUDGET_EXHAUSTED
        if job.terminal_at is None:
            job.terminal_at = now
    else:
        job.state = "manual_retry_required"
        job.terminal_at = None
        job.terminal_reason = None
        job.last_error = "Memory generation requires an explicit claim retry."
