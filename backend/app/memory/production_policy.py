from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class ImportanceLevel(_PolicyModel):
    name: NonEmptyText
    criteria: NonEmptyText
    examples: NonEmptyText

    @field_validator("name", "criteria", "examples")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be empty or whitespace")
        return value


class FactsPolicy(_PolicyModel):
    max_per_batch: Annotated[int, Field(ge=0)]
    importance_levels: tuple[ImportanceLevel, ...]

    @field_validator("importance_levels", mode="before")
    @classmethod
    def freeze_levels(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_importance_levels(self) -> Self:
        names = [level.name for level in self.importance_levels]
        if not names or len(names) != len(set(names)):
            raise ValueError("importance levels must be nonempty with unique names")
        return self


class GlobalPolicy(_PolicyModel):
    target_words: Annotated[int, Field(gt=0)]


class JobsPolicy(_PolicyModel):
    max_attempts: Annotated[int, Field(gt=0)]
    retry_backoff_seconds: tuple[Annotated[float, Field(ge=0)], ...]
    request_timeout_seconds: Annotated[float, Field(gt=0)]
    lease_seconds: Annotated[float, Field(gt=0)]
    poll_seconds: Annotated[float, Field(gt=0)]

    @field_validator("retry_backoff_seconds", mode="before")
    @classmethod
    def freeze_backoff(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def validate_retry_and_lease(self) -> Self:
        if len(self.retry_backoff_seconds) != self.max_attempts - 1:
            raise ValueError("retry backoff count must equal max attempts minus one")
        if not all(math.isfinite(delay) for delay in self.retry_backoff_seconds):
            raise ValueError("retry backoff values must be finite")
        if self.lease_seconds <= self.request_timeout_seconds:
            raise ValueError("lease must exceed request timeout")
        return self


class AdmissionPolicy(_PolicyModel):
    wait_timeout_seconds: Annotated[float, Field(gt=0)]


class MemoryProductionPolicy(_PolicyModel):
    raw_turns: Annotated[int, Field(ge=0)]
    batch_turns: Annotated[int, Field(gt=0)]
    intermediate_limit: Annotated[int, Field(ge=0)]
    backlog_batches: Annotated[int, Field(ge=0)]
    facts: FactsPolicy
    global_: GlobalPolicy = Field(alias="global")
    jobs: JobsPolicy
    admission: AdmissionPolicy

    def policy_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def configured_facts_policy(*, max_per_batch: int) -> FactsPolicy:
    from app.config_loader import load_saga_config

    levels = load_saga_config()["memory"]["production"]["facts"]["importance_levels"]
    return FactsPolicy.model_validate(
        {"max_per_batch": max_per_batch, "importance_levels": levels}
    )
