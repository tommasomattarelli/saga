from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from google.genai.errors import APIError as GoogleAPIError
from openai import APIStatusError
from pydantic import BaseModel

from app.ai.generation_contracts import (
    GenerationRequest,
    RawGenerationReceipt,
)
from app.ai.generation_correction import CorrectionFailure
from app.ai.generation_errors import (
    Adapter,
    FailureAction,
    FailureSignals,
    SchemaModeUnsupportedBeforeIO,
    classify_failure,
)
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationExecutionError,
    GenerationExecutionIdentity,
    GenerationLedger,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    GenerationSendKind,
    SendOutcome,
)
from app.ai.generation_execution_recovery import (
    correction_candidate,
    correction_request,
    next_fallback,
    record_uncertain,
    resume_generation,
)
from app.ai.providers.local import OpenAICompatibleResponseError
from app.ai.response_validation import (
    Normalization,
    ResponseValidationError,
    ValidatedResponse,
)


class GenerationProvider(Protocol):
    async def send(self, request: GenerationRequest) -> RawGenerationReceipt: ...


@dataclass(frozen=True)
class GenerationExecutionResult[T: BaseModel]:
    value: T
    identity: GenerationExecutionIdentity
    sends: tuple[SendOutcome, ...]
    normalization: Normalization


async def execute_generation[T: BaseModel](
    base: GenerationRequest,
    provider: GenerationProvider,
    ledger: GenerationLedger,
    policy: GenerationRecoveryPolicy,
    adapter: Adapter,
    *,
    validator: Callable[[RawGenerationReceipt, GenerationRequest], ValidatedResponse[T]],
) -> GenerationExecutionResult[T]:
    execution_identity = GenerationExecutionIdentity.create(base.identity, policy)
    identity = execution_identity.digest
    replay = await resume_generation(base, await ledger.history(identity, base.role), validator)
    outcomes = list(replay.outcomes)
    if replay.validated is not None:
        return GenerationExecutionResult(
            replay.validated.model,
            execution_identity,
            tuple(outcomes),
            replay.validated.normalization,
        )
    failures = list(replay.failures)
    request = replay.request
    send_kind = replay.send_kind
    while True:
        attempt = GenerationAttempt(
            request.identity.digest,
            request.format_mode,
            send_kind,
        )
        reservation = await ledger.reserve(
            identity,
            base.role,
            policy.max_sends_per_result,
            attempt,
        )
        try:
            receipt = await provider.send(request)
        except SchemaModeUnsupportedBeforeIO as error:
            if type(error) is not SchemaModeUnsupportedBeforeIO:
                outcome = SendOutcome(
                    reservation,
                    GenerationOutcomeStatus.STOP,
                    reason="internal_failure",
                )
                await ledger.record(identity, base.role, outcome)
                raise GenerationExecutionError(
                    "Generation failed and must not be retried automatically."
                ) from None
            classification = classify_failure(
                FailureSignals(adapter=adapter, pre_io_schema_incompatibility=True)
            )
            if classification.action is not FailureAction.FALLBACK:
                outcome = SendOutcome(
                    reservation,
                    GenerationOutcomeStatus.STOP,
                    reason=classification.reason,
                )
                await ledger.record(identity, base.role, outcome)
                raise GenerationExecutionError(classification.message) from None
            outcome = SendOutcome(
                reservation,
                GenerationOutcomeStatus.SCHEMA_MODE_UNSUPPORTED,
                reason=classification.reason,
            )
            await ledger.record(identity, base.role, outcome)
            outcomes.append(outcome)
            fallback = next_fallback(base, request.format_mode)
            if fallback is None:
                raise GenerationExecutionError(
                    "No authorized schema fallback is available."
                ) from None
            request = correction_request(base, tuple(failures), fallback)
            send_kind = GenerationSendKind.FALLBACK
            continue
        except asyncio.CancelledError:
            await record_uncertain(ledger, identity, base.role, reservation)
            raise
        except Exception as error:
            signals = _exception_signals(adapter, error)
            classification = classify_failure(signals)
            retryable = classification.action in {
                FailureAction.RETRY,
                FailureAction.RATE_LIMIT,
            }
            status = {
                FailureAction.RETRY: GenerationOutcomeStatus.RETRY,
                FailureAction.RATE_LIMIT: GenerationOutcomeStatus.RATE_LIMIT,
            }.get(classification.action, GenerationOutcomeStatus.STOP)
            outcome = SendOutcome(
                reservation,
                status,
                reason=classification.reason,
            )
            await ledger.record(identity, base.role, outcome)
            outcomes.append(outcome)
            if not retryable:
                raise GenerationExecutionError(classification.message) from None
            send_kind = GenerationSendKind.TRANSPORT_RETRY
            continue

        finish = (receipt.finish_reason or "").upper()
        terminal_finish = finish in {
            "CONTENT_FILTER",
            "LENGTH",
            "MAX_TOKENS",
            "SAFETY",
            "RECITATION",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "LANGUAGE",
        }
        classification = classify_failure(
            FailureSignals(
                adapter=adapter,
                refusal=bool(receipt.refusal),
                prompt_blocked=bool(receipt.blocked_reason),
                finish_reason=receipt.finish_reason if terminal_finish else None,
            )
        )
        if (
            receipt.refusal or receipt.blocked_reason or terminal_finish
        ) and classification.action in {
            FailureAction.REFUSAL,
            FailureAction.TRUNCATED,
            FailureAction.STOP,
        }:
            status = (
                GenerationOutcomeStatus.REFUSAL
                if classification.action is FailureAction.REFUSAL
                else GenerationOutcomeStatus.TRUNCATED
                if classification.action is FailureAction.TRUNCATED
                else GenerationOutcomeStatus.STOP
            )
            outcome = SendOutcome(
                reservation,
                status,
                receipt=receipt,
                reason=classification.reason,
            )
            await ledger.record(identity, base.role, outcome)
            outcomes.append(outcome)
            raise GenerationExecutionError(classification.message)
        try:
            validated = validator(receipt, request)
        except asyncio.CancelledError:
            await record_uncertain(ledger, identity, base.role, reservation, receipt)
            raise
        except ResponseValidationError as error:
            candidate = correction_candidate(receipt)
            outcome = SendOutcome(
                reservation,
                GenerationOutcomeStatus.INVALID,
                receipt=receipt,
                reason="validation_failed",
                diagnostics=error.diagnostics,
                normalization=error.normalization,
            )
            await ledger.record(identity, base.role, outcome)
            outcomes.append(outcome)
            if candidate is None:
                raise GenerationExecutionError(
                    "The invalid response has no complete correction candidate."
                ) from None
            failure = CorrectionFailure(
                candidate,
                error.diagnostics,
                error.normalization,
            )
            failures.append(failure)
            request = correction_request(base, tuple(failures), request.format_mode)
            send_kind = GenerationSendKind.CORRECTION
            continue
        except Exception:
            await ledger.record(
                identity,
                base.role,
                SendOutcome(
                    reservation,
                    GenerationOutcomeStatus.INTERNAL_FAILURE,
                    receipt=receipt,
                    reason="validator_failure",
                ),
            )
            raise GenerationExecutionError("Generation validation failed internally.") from None
        outcome = SendOutcome(
            reservation,
            GenerationOutcomeStatus.VALID,
            receipt=receipt,
            normalization=validated.normalization,
        )
        await ledger.record(identity, base.role, outcome)
        outcomes.append(outcome)
        return GenerationExecutionResult(
            validated.model,
            execution_identity,
            tuple(outcomes),
            validated.normalization,
        )


def _exception_signals(adapter: Adapter, error: Exception) -> FailureSignals:
    if type(error) is OpenAICompatibleResponseError:
        return FailureSignals(
            adapter=adapter,
            code=error.code,
            status=error.status,
            error_type=error.error_type,
        )
    if isinstance(error, APIStatusError):
        body = error.body
        details = body.get("error", body) if isinstance(body, dict) else None
        fields = details if isinstance(details, dict) else {}
        code = fields.get("code")
        error_type = fields.get("type")
        return FailureSignals(
            adapter=adapter,
            http_status=error.status_code,
            code=code if isinstance(code, str | int) else None,
            error_type=error_type if isinstance(error_type, str) else None,
            exception=error,
        )
    if isinstance(error, GoogleAPIError):
        return FailureSignals(
            adapter=adapter,
            http_status=error.code,
            status=error.status,
            exception=error,
        )
    return FailureSignals(adapter=adapter, exception=error)
