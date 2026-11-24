from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.ai.generation_contracts import GenerationIdentity, OutputLimit
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationExecutionError,
    GenerationExecutionIdentity,
    GenerationLedger,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    GenerationSend,
    GenerationSendKind,
    SendOutcome,
    SendReservation,
)
from app.ai.response_validation import DiagnosticCode, Normalization, ValidationDiagnostic
from app.memory.generation_receipts import decode_receipt, encode_receipt
from app.memory.job_claims import JobClaim, load_claim
from app.memory.job_contracts import (
    MemoryGenerationIdentitySnapshot,
    MemoryGenerationRequestIdentitySnapshot,
    MemoryJobExecutionIdentity,
)
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob


class DurableMemoryGenerationLedger(GenerationLedger):
    def __init__(self, claim: JobClaim) -> None:
        self.claim = claim

    async def _load(
        self, db: AsyncSession, identity: str, role: str
    ) -> tuple[MemoryJob, MemoryGenerationIdentitySnapshot]:
        loaded = await load_claim(db, self.claim)
        if loaded is None:
            raise GenerationExecutionError("Memory generation claim is no longer valid.")
        job, _, _ = loaded
        if job.execution_contract_version != 1 or job.execution_identity is None:
            raise GenerationExecutionError("Memory generation identity is unavailable.")
        frozen = MemoryJobExecutionIdentity.model_validate(job.execution_identity)
        if job.execution_identity_hash is None or job.execution_identity_version is None:
            raise GenerationExecutionError("Memory generation identity is unavailable.")
        frozen.verify(job.execution_identity_version, job.execution_identity_hash)
        snapshot = frozen.result_identities.get(role)
        if snapshot is None:
            raise GenerationExecutionError("Memory generation role is not frozen.")
        fields = snapshot.model_dump(exclude={"request_identity_hash"})
        fields["output_limit"] = OutputLimit(**snapshot.output_limit.model_dump())
        base = GenerationIdentity(**fields)
        expected = GenerationExecutionIdentity.create(
            base, GenerationRecoveryPolicy(frozen.max_sends_per_result)
        ).digest
        if expected != identity:
            raise GenerationExecutionError("Memory generation execution identity changed.")
        return job, snapshot

    async def reserve(
        self, identity: str, role: str, max_sends: int, attempt: GenerationAttempt
    ) -> SendReservation:
        async with dependencies.async_session() as db, db.begin():
            job, frozen = await self._load(db, identity, role)
            request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
                attempt.request_identity_snapshot
            )
            fixed_fields = (
                "format_version",
                "role",
                "logical_result_id",
                "contract_name",
                "contract_version",
                "contract_schema_hash",
                "effective_schema_hash",
                "wire_encoding_version",
                "wire_schema_hash",
                "tool_declarations_hash",
                "contextual_validator_version",
                "provider",
                "model",
                "destination_fingerprint",
                "output_limit",
                "allow_json_mode_fallback",
                "allow_prompt_only_fallback",
                "session_affinity",
            )
            if (
                request.digest != attempt.request_identity
                or request.role != role
                or request.format_mode != attempt.format_mode
                or any(getattr(request, name) != getattr(frozen, name) for name in fixed_fields)
                or (
                    attempt.send_kind is GenerationSendKind.INITIAL
                    and request.digest != frozen.request_identity_hash
                )
            ):
                raise GenerationExecutionError("Memory generation request identity is invalid.")
            execution_identity = job.execution_identity
            if execution_identity is None or max_sends != execution_identity.max_sends_per_result:
                raise GenerationExecutionError("Memory generation send budget changed.")
            rows = list(
                await db.scalars(
                    select(MemoryGeneration)
                    .where(MemoryGeneration.job_id == job.id, MemoryGeneration.role == role)
                    .order_by(MemoryGeneration.send_number)
                )
            )
            if [row.send_number for row in rows] != list(range(1, len(rows) + 1)):
                raise GenerationExecutionError("Stored generation send history is invalid.")
            if len(rows) >= max_sends:
                raise GenerationExecutionError("Generation send budget exhausted.")
            number = len(rows) + 1
            db.add(
                MemoryGeneration(
                    id=uuid4(),
                    job_id=job.id,
                    attempt_id=self.claim.attempt_id,
                    campaign_id=job.campaign_id,
                    policy_id=job.policy_id,
                    batch_id=job.batch_id,
                    role=role,
                    provider=request.provider,
                    model=request.model,
                    send_number=number,
                    send_kind=attempt.send_kind.value,
                    request_identity_hash=request.digest,
                    request_identity_snapshot=request.snapshot_json,
                    format_mode=request.format_mode,
                )
            )
            await db.flush()
            return SendReservation(number, attempt)

    async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
        async with dependencies.async_session() as db, db.begin():
            job, _ = await self._load(db, identity, role)
            row = await db.scalar(
                select(MemoryGeneration)
                .where(
                    MemoryGeneration.job_id == job.id,
                    MemoryGeneration.role == role,
                    MemoryGeneration.send_number == outcome.reservation.number,
                )
                .with_for_update()
            )
            reservation = outcome.reservation
            if (
                row is None
                or row.attempt_id != self.claim.attempt_id
                or row.request_identity_hash != reservation.attempt.request_identity
                or row.request_identity_snapshot != reservation.attempt.request_identity_snapshot
                or row.format_mode != reservation.attempt.format_mode
                or row.send_kind != reservation.attempt.send_kind.value
                or row.status is not None
            ):
                raise GenerationExecutionError("Generation reservation cannot be recorded.")
            receipt, candidate = (
                encode_receipt(outcome.receipt) if outcome.receipt is not None else (None, None)
            )
            usage = outcome.receipt.usage if outcome.receipt else None
            row.status = outcome.status.value
            row.outcome_reason = outcome.reason
            row.receipt = receipt
            row.raw_candidate = candidate
            row.raw_candidate_hash = (
                hashlib.sha256(candidate.encode()).hexdigest() if candidate is not None else None
            )
            row.diagnostics = [
                [item.code.value, list(item.path)] for item in outcome.diagnostics
            ] or None
            row.normalization = outcome.normalization.value if outcome.normalization else None
            row.input_tokens = usage.input_tokens if usage else None
            row.output_tokens = usage.output_tokens if usage else None
            row.cost = Decimal(str(usage.cost)) if usage and usage.cost is not None else None

    async def history(self, identity: str, role: str) -> tuple[GenerationSend, ...]:
        async with dependencies.async_session() as db, db.begin():
            job, _ = await self._load(db, identity, role)
            rows = list(
                await db.scalars(
                    select(MemoryGeneration)
                    .where(MemoryGeneration.job_id == job.id, MemoryGeneration.role == role)
                    .order_by(MemoryGeneration.send_number)
                )
            )
            history = []
            for number, row in enumerate(rows, start=1):
                if (
                    row.send_number != number
                    or row.role != role
                    or row.send_kind is None
                    or row.request_identity_hash is None
                    or row.request_identity_snapshot is None
                    or row.format_mode is None
                ):
                    raise GenerationExecutionError("Stored generation history is invalid.")
                request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
                    row.request_identity_snapshot
                )
                if (
                    request.digest != row.request_identity_hash
                    or request.snapshot_json != row.request_identity_snapshot
                    or request.role != role
                    or request.provider != row.provider
                    or request.model != row.model
                    or request.format_mode != row.format_mode
                ):
                    raise GenerationExecutionError("Stored generation history is invalid.")
                attempt = GenerationAttempt(
                    request.digest,
                    request.snapshot_json,
                    request.format_mode,
                    GenerationSendKind(row.send_kind),
                )
                reservation = SendReservation(row.send_number, attempt)
                outcome = None
                if row.status is not None:
                    try:
                        status = GenerationOutcomeStatus(row.status)
                    except ValueError:
                        raise GenerationExecutionError(
                            "Stored generation outcome is invalid."
                        ) from None
                    receipt = (
                        decode_receipt(row.receipt, row.raw_candidate)
                        if row.receipt is not None
                        else None
                    )
                    outcome = SendOutcome(
                        reservation,
                        status,
                        receipt=receipt,
                        reason=row.outcome_reason,
                        diagnostics=_decode_diagnostics(row.diagnostics),
                        normalization=_decode_normalization(row.normalization),
                    )
                history.append(GenerationSend(reservation, outcome))
            return tuple(history)


def _decode_diagnostics(value: object) -> tuple[ValidationDiagnostic, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GenerationExecutionError("Stored generation diagnostics are invalid.")
    try:
        decoded = []
        for item in cast(list[object], value):
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], list)
                or any(
                    not isinstance(segment, (str, int)) or isinstance(segment, bool)
                    for segment in item[1]
                )
            ):
                raise ValueError
            decoded.append(ValidationDiagnostic(DiagnosticCode(item[0]), tuple(item[1])))
        return tuple(decoded)
    except (TypeError, ValueError, IndexError) as exc:
        raise GenerationExecutionError("Stored generation diagnostics are invalid.") from exc


def _decode_normalization(value: str | None) -> Normalization | None:
    if value is None:
        return None
    try:
        return Normalization(value)
    except ValueError as exc:
        raise GenerationExecutionError("Stored generation normalization is invalid.") from exc
