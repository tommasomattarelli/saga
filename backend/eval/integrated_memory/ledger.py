"""Durable, fail-closed outbound request budget for integrated-memory evals."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator

Kind = Literal["generation", "embedding"]


class LedgerBlockedError(RuntimeError):
    pass


class AttemptScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_id: str
    campaign_id: UUID
    job_id: UUID | None = None
    batch_id: UUID | None = None
    source_turn_ids: tuple[UUID, ...]
    input_hash: str
    role: Literal["summary", "facts", "global", "unified", "embedding"]
    provider: str
    model: str
    index_id: UUID | None = None
    source_embedding_ids: tuple[UUID, ...] = ()


class _Header(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event: Literal["header"]
    version: Literal[1]
    caps: dict[str, int]
    run_seal: str


class _Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event: Literal["reserve"]
    attempt_id: str
    kind: Kind
    metadata: dict[str, str]
    texts: int = Field(ge=0)

    @field_validator("texts")
    @classmethod
    def validate_text_count(cls, value: int, info: ValidationInfo) -> int:
        if info.data.get("kind") == "generation" and value:
            raise ValueError("generation attempts cannot contain embedding texts")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {
            "provider",
            "model",
            "input_hash",
            "request_input_hash",
            "space",
            "run_id",
            "campaign_id",
            "job_id",
            "batch_id",
            "source_turn_ids",
            "role",
            "index_id",
            "source_embedding_ids",
        }
        if not value or any(key not in allowed for key in value):
            raise ValueError("unsupported request metadata")
        return value


class _Finish(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    event: Literal["complete", "failure", "failure_retry", "cancelled"]
    attempt_id: str


class IntegratedLedger:
    def __init__(
        self, path: Path, *, generation_cap: int, embedding_cap: int, text_cap: int, run_seal: str
    ) -> None:
        if min(generation_cap, embedding_cap, text_cap) < 0 or not run_seal:
            raise ValueError("caps must be nonnegative and run_seal must be nonempty")
        self.path = path
        self.caps = {"generation": generation_cap, "embedding": embedding_cap, "texts": text_cap}
        self.run_seal = run_seal
        self.counts = {"generation": 0, "embedding": 0, "texts": 0}
        self._pending: str | None = None
        self._failed = False
        self._blocked = False
        self._seen_ids: set[str] = set()
        self._scope: AttemptScope | None = None
        if path.exists():
            self._load()
        else:
            self._append(
                _Header(event="header", version=1, caps=self.caps, run_seal=run_seal).model_dump()
            )

    def _append(self, row: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8").splitlines()
            if not raw:
                raise ValueError
            header = _Header.model_validate(json.loads(raw[0], object_pairs_hook=_unique_object))
            if header.caps != self.caps or header.run_seal != self.run_seal:
                raise ValueError
            expected = {
                "event": "header",
                "version": 1,
                "caps": self.caps,
                "run_seal": self.run_seal,
            }
            if header.model_dump() != expected:
                raise ValueError
            for encoded in raw[1:]:
                row = json.loads(encoded, object_pairs_hook=_unique_object)
                if self._pending is None:
                    if self._failed:
                        raise ValueError
                    reservation = _Reservation.model_validate(row)
                    if reservation.attempt_id in self._seen_ids:
                        raise ValueError
                    self._seen_ids.add(reservation.attempt_id)
                    self._pending = reservation.attempt_id
                    self.counts[reservation.kind] += 1
                    self.counts["texts"] += reservation.texts
                else:
                    finish = _Finish.model_validate(row)
                    if finish.attempt_id != self._pending:
                        raise ValueError
                    self._pending = None
                    self._failed = finish.event != "complete"
            if (
                self._pending is not None
                or self._failed
                or any(self.counts[k] > v for k, v in self.caps.items())
            ):
                raise ValueError
        except (
            OSError,
            ValueError,
            ValidationError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise LedgerBlockedError(
                "integrated evaluation ledger is invalid, interrupted, or failed"
            ) from exc

    @contextmanager
    def scope(self, scope: AttemptScope) -> Iterator[None]:
        previous, self._scope = self._scope, scope
        try:
            yield
        finally:
            self._scope = previous

    @property
    def current_scope(self) -> AttemptScope | None:
        return self._scope

    def require_scope(self, *, provider: str, model: str) -> AttemptScope:
        scope = self._scope
        if scope is None or scope.provider != provider or scope.model != model:
            raise LedgerBlockedError(
                "request provider/model do not match the active attempt scope"
            )
        return scope

    def reserve(self, kind: Kind, metadata: dict[str, str], *, texts: int) -> None:
        self.ensure_healthy()
        if (
            kind not in ("generation", "embedding")
            or texts < 0
            or (kind == "generation" and texts != 0)
        ):
            raise LedgerBlockedError("invalid outbound request reservation")
        if any(
            key not in {"provider", "model", "input_hash", "space"} or not isinstance(value, str)
            for key, value in metadata.items()
        ):
            raise LedgerBlockedError("outbound request metadata contains unsupported fields")
        if (
            self.counts[kind] + 1 > self.caps[kind]
            or self.counts["texts"] + texts > self.caps["texts"]
        ):
            self._blocked = True
            raise LedgerBlockedError("integrated evaluation request budget exhausted")
        scope = self._scope
        scoped = scope.model_dump(mode="json") if scope else {}
        if scope is not None:
            if metadata.get("provider") == "local":
                metadata = {**metadata, "provider": scope.provider}
            self.require_scope(
                provider=metadata.get("provider", ""), model=metadata.get("model", "")
            )
        attempt_id = uuid4().hex
        merged_metadata = {
            **metadata,
            **{
                key: json.dumps(value, sort_keys=True)
                if isinstance(value, (dict, list))
                else str(value)
                for key, value in scoped.items()
            },
        }
        if scope is not None and "input_hash" in metadata:
            merged_metadata["request_input_hash"] = metadata["input_hash"]
            merged_metadata["input_hash"] = scope.input_hash
        self._append(
            _Reservation(
                event="reserve",
                attempt_id=attempt_id,
                kind=kind,
                metadata=merged_metadata,
                texts=texts,
            ).model_dump()
        )
        self.counts[kind] += 1
        self.counts["texts"] += texts
        self._pending = attempt_id
        self._seen_ids.add(attempt_id)

    def _finish(self, event: Literal["complete", "failure", "failure_retry", "cancelled"]) -> None:
        if self._pending is None:
            raise LedgerBlockedError("no outbound request is pending")
        attempt_id = self._pending
        self._append(_Finish(event=event, attempt_id=attempt_id).model_dump())
        self._pending = None
        self._failed = event in ("failure", "cancelled")

    def complete(self) -> None:
        self._finish("complete")

    def fail(self, *, retrying: bool = False) -> None:
        self._finish("failure_retry" if retrying else "failure")

    def cancel(self) -> None:
        self._finish("cancelled")

    def ensure_healthy(self) -> None:
        if self._pending is not None or self._failed or self._blocked:
            raise LedgerBlockedError(
                "integrated evaluation ledger is latched after an uncertain or failed request"
            )

    def latch(self) -> None:
        self._blocked = True


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate ledger field")
        result[key] = value
    return result
