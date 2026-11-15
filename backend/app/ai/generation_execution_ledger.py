from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from app.ai.generation_contracts import (
    FormatMode,
    GenerationIdentity,
    RawGenerationReceipt,
)
from app.ai.response_validation import Normalization, ValidationDiagnostic


class GenerationExecutionError(Exception):
    pass


@dataclass(frozen=True)
class GenerationRecoveryPolicy:
    max_sends_per_result: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_sends_per_result, bool)
            or not isinstance(self.max_sends_per_result, int)
            or self.max_sends_per_result < 1
        ):
            raise ValueError("Generation send limit must be a positive integer.")


@dataclass(frozen=True)
class GenerationExecutionIdentity:
    version: int
    base_identity: GenerationIdentity
    recovery_policy: GenerationRecoveryPolicy

    @classmethod
    def create(
        cls, base_identity: GenerationIdentity, policy: GenerationRecoveryPolicy
    ) -> GenerationExecutionIdentity:
        return cls(1, base_identity, policy)

    @property
    def digest(self) -> str:
        snapshot = {
            "version": self.version,
            "base_identity": json.loads(self.base_identity.snapshot_json),
            "max_sends_per_result": self.recovery_policy.max_sends_per_result,
        }
        return hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class GenerationAttempt:
    request_identity: str
    request_identity_snapshot: str
    format_mode: FormatMode
    send_kind: GenerationSendKind


class GenerationSendKind(StrEnum):
    INITIAL = "initial"
    CORRECTION = "correction"
    FALLBACK = "fallback"
    TRANSPORT_RETRY = "transport_retry"


class GenerationOutcomeStatus(StrEnum):
    SCHEMA_MODE_UNSUPPORTED = "schema_mode_unsupported"
    RETRY = "retry"
    RATE_LIMIT = "rate_limit"
    INVALID = "invalid"
    VALID = "valid"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    STOP = "stop"
    INTERNAL_FAILURE = "internal_failure"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class SendReservation:
    number: int
    attempt: GenerationAttempt


@dataclass(frozen=True)
class SendOutcome:
    reservation: SendReservation
    status: GenerationOutcomeStatus
    receipt: RawGenerationReceipt | None = field(default=None, repr=False)
    reason: str | None = None
    diagnostics: tuple[ValidationDiagnostic, ...] = ()
    normalization: Normalization | None = None


@dataclass(frozen=True)
class GenerationSend:
    reservation: SendReservation
    outcome: SendOutcome | None


class GenerationLedger(Protocol):
    async def reserve(
        self,
        identity: str,
        role: str,
        max_sends: int,
        attempt: GenerationAttempt,
    ) -> SendReservation: ...

    async def record(self, identity: str, role: str, outcome: SendOutcome) -> None: ...

    async def history(self, identity: str, role: str) -> tuple[GenerationSend, ...]: ...


class InMemoryGenerationLedger:
    def __init__(self) -> None:
        self._sends: dict[tuple[str, str], list[GenerationSend]] = {}

    async def reserve(
        self,
        identity: str,
        role: str,
        max_sends: int,
        attempt: GenerationAttempt,
    ) -> SendReservation:
        sends = self._sends.setdefault((identity, role), [])
        if len(sends) >= max_sends:
            raise GenerationExecutionError("Generation send budget exhausted.")
        reservation = SendReservation(len(sends) + 1, attempt)
        sends.append(GenerationSend(reservation, None))
        return reservation

    async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
        sends = self._sends[(identity, role)]
        index = outcome.reservation.number - 1
        reserved = sends[index]
        if reserved.outcome is not None or reserved.reservation != outcome.reservation:
            raise GenerationExecutionError("Generation send outcome is already recorded.")
        sends[index] = GenerationSend(reserved.reservation, outcome)

    async def history(self, identity: str, role: str) -> tuple[GenerationSend, ...]:
        return tuple(self._sends.get((identity, role), ()))

    def send_count(self, identity: str, role: str) -> int:
        return len(self._sends.get((identity, role), ()))
