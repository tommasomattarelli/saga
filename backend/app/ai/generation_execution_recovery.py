from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.ai.generation_contracts import FormatMode, GenerationRequest, RawGenerationReceipt
from app.ai.generation_correction import CorrectionFailure, build_correction_request
from app.ai.generation_execution_ledger import (
    GenerationExecutionError,
    GenerationLedger,
    GenerationOutcomeStatus,
    GenerationSend,
    GenerationSendKind,
    SendOutcome,
    SendReservation,
)
from app.ai.response_validation import Normalization, ValidatedResponse


@dataclass(frozen=True)
class RecoveryState[T: BaseModel]:
    request: GenerationRequest
    failures: tuple[CorrectionFailure, ...]
    outcomes: tuple[SendOutcome, ...]
    send_kind: GenerationSendKind
    validated: ValidatedResponse[T] | None = None


async def resume_generation[T: BaseModel](
    base: GenerationRequest,
    history: tuple[GenerationSend, ...],
    validator: Callable[[RawGenerationReceipt, GenerationRequest], ValidatedResponse[T]],
) -> RecoveryState[T]:
    failures: list[CorrectionFailure] = []
    outcomes: list[SendOutcome] = []
    request = base
    send_kind = GenerationSendKind.INITIAL
    for number, entry in enumerate(history, start=1):
        if entry.reservation.number != number or entry.outcome is None:
            raise GenerationExecutionError(
                "A generation send has an uncertain outcome and cannot be replayed."
            )
        attempt = entry.reservation.attempt
        if (
            attempt.request_identity != request.identity.digest
            or attempt.format_mode is not request.format_mode
            or attempt.send_kind is not send_kind
        ):
            raise GenerationExecutionError(
                "Generation history does not match its frozen request derivation."
            )
        outcome = entry.outcome
        outcomes.append(outcome)
        if outcome.status == "valid":
            if outcome.receipt is None:
                raise GenerationExecutionError("A valid candidate is unavailable for reuse.")
            try:
                validated = validator(outcome.receipt, request)
            except Exception:
                raise GenerationExecutionError(
                    "A recorded generation candidate no longer validates."
                ) from None
            return RecoveryState(request, tuple(failures), tuple(outcomes), send_kind, validated)
        if outcome.status == "invalid":
            if outcome.receipt is None:
                raise GenerationExecutionError("A failed generation candidate is unavailable.")
            candidate = correction_candidate(outcome.receipt)
            if candidate is None:
                raise GenerationExecutionError(
                    "A failed generation has no complete correction history."
                )
            failures.append(
                CorrectionFailure(
                    candidate,
                    outcome.diagnostics,
                    outcome.normalization or Normalization.NONE,
                )
            )
            request = correction_request(base, tuple(failures), request.format_mode)
            send_kind = GenerationSendKind.CORRECTION
            continue
        if outcome.status == "schema_mode_unsupported":
            fallback = next_fallback(base, request.format_mode)
            if fallback is None:
                raise GenerationExecutionError("No authorized schema fallback is available.")
            request = correction_request(base, tuple(failures), fallback)
            send_kind = GenerationSendKind.FALLBACK
            continue
        if outcome.status in {"retry", "rate_limit"}:
            send_kind = GenerationSendKind.TRANSPORT_RETRY
            continue
        raise GenerationExecutionError(
            "Generation history contains an outcome that cannot be retried automatically."
        )
    return RecoveryState(request, tuple(failures), tuple(outcomes), send_kind)


def correction_request(
    base: GenerationRequest,
    failures: tuple[CorrectionFailure, ...],
    format_mode: FormatMode,
) -> GenerationRequest:
    if failures:
        return build_correction_request(base, failures, format_mode=format_mode).request
    if format_mode is base.format_mode:
        return base
    return base.derive(messages=base.messages, format_mode=format_mode)


def correction_candidate(receipt: RawGenerationReceipt) -> str | None:
    if receipt.raw_candidate is not None:
        return receipt.raw_candidate
    if not receipt.tool_calls:
        return receipt.text
    return None


def next_fallback(base: GenerationRequest, mode: FormatMode) -> FormatMode | None:
    if mode is FormatMode.STRICT_NATIVE and base.allow_json_mode_fallback:
        return FormatMode.JSON_MODE
    if (
        mode in {FormatMode.STRICT_NATIVE, FormatMode.JSON_MODE}
        and base.allow_prompt_only_fallback
    ):
        return FormatMode.PROMPT_ONLY
    return None


async def record_uncertain(
    ledger: GenerationLedger,
    identity: str,
    role: str,
    reservation: SendReservation,
    receipt: RawGenerationReceipt | None = None,
) -> None:
    try:
        await ledger.record(
            identity,
            role,
            SendOutcome(reservation, GenerationOutcomeStatus.UNCERTAIN, receipt=receipt),
        )
    except Exception:
        return
