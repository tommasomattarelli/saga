from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from types import MappingProxyType

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
    model_validator,
)

from app.ai.generation_contracts import FormatMode

_IDENTITY_VERSION = 1
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class MemoryOutputLimitSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    configured_ceiling: StrictInt = Field(gt=0)
    known_lower_limit: StrictInt | None = Field(default=None, gt=0)
    limit_source: StrictStr | None = None

    @model_validator(mode="after")
    def validate_limit_source(self) -> MemoryOutputLimitSnapshot:
        if (self.known_lower_limit is None) != (self.limit_source is None):
            raise ValueError("A known lower limit and its source must be stored together.")
        if self.limit_source == "":
            raise ValueError("A known lower limit source cannot be empty.")
        return self


class MemoryGenerationIdentitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format_version: StrictInt = Field(gt=0)
    role: StrictStr = Field(min_length=1)
    logical_result_id: StrictStr = Field(min_length=1)
    initial_prefix_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    contract_name: StrictStr = Field(min_length=1)
    contract_version: StrictStr = Field(min_length=1)
    contract_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    effective_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    wire_encoding_version: StrictStr = Field(min_length=1)
    wire_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    tool_declarations_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    contextual_validator_version: StrictStr = Field(min_length=1)
    provider: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    destination_fingerprint: StrictStr = Field(min_length=1)
    output_limit: MemoryOutputLimitSnapshot
    request_identity_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    format_mode: FormatMode
    allow_json_mode_fallback: StrictBool
    allow_prompt_only_fallback: StrictBool
    session_affinity: StrictStr | None

    @field_validator("session_affinity")
    @classmethod
    def require_nonempty_affinity(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Session affinity cannot be empty.")
        return value


class MemoryGenerationRequestIdentitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: StrictInt = Field(gt=0)
    role: StrictStr = Field(min_length=1)
    logical_result_id: StrictStr = Field(min_length=1)
    initial_prefix_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    contract_name: StrictStr = Field(min_length=1)
    contract_version: StrictStr = Field(min_length=1)
    contract_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    effective_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    wire_encoding_version: StrictStr = Field(min_length=1)
    wire_schema_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    tool_declarations_hash: StrictStr = Field(pattern=_HASH_PATTERN)
    contextual_validator_version: StrictStr = Field(min_length=1)
    provider: StrictStr = Field(min_length=1)
    model: StrictStr = Field(min_length=1)
    destination_fingerprint: StrictStr = Field(min_length=1)
    output_limit: MemoryOutputLimitSnapshot
    format_mode: FormatMode
    allow_json_mode_fallback: StrictBool
    allow_prompt_only_fallback: StrictBool
    session_affinity: StrictStr | None

    @field_validator("session_affinity")
    @classmethod
    def require_nonempty_affinity(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Session affinity cannot be empty.")
        return value

    @property
    def snapshot_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.snapshot_json.encode()).hexdigest()


class MemoryJobExecutionIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result_identities: Mapping[StrictStr, MemoryGenerationIdentitySnapshot]
    max_sends_per_result: StrictInt = Field(gt=0)

    @field_validator("result_identities", mode="after")
    @classmethod
    def freeze_result_identities(
        cls, value: Mapping[str, MemoryGenerationIdentitySnapshot]
    ) -> Mapping[str, MemoryGenerationIdentitySnapshot]:
        return MappingProxyType(dict(value))

    @field_serializer("result_identities")
    def serialize_result_identities(
        self, value: Mapping[str, MemoryGenerationIdentitySnapshot]
    ) -> dict[str, MemoryGenerationIdentitySnapshot]:
        return dict(value)

    @model_validator(mode="after")
    def validate_result_identities(self) -> MemoryJobExecutionIdentity:
        if not self.result_identities:
            raise ValueError("A memory job requires at least one result identity.")
        if any(role != identity.role for role, identity in self.result_identities.items()):
            raise ValueError("Memory result identity keys must match their roles.")
        return self

    def digest(self, version: int) -> str:
        if version != _IDENTITY_VERSION:
            raise ValueError("Unsupported memory job execution identity version.")
        snapshot = {
            "version": version,
            "result_identities": {
                role: identity.model_dump(mode="json")
                for role, identity in self.result_identities.items()
            },
            "max_sends_per_result": self.max_sends_per_result,
        }
        return hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def verify(self, version: int, expected_hash: str) -> None:
        if re.fullmatch(_HASH_PATTERN, expected_hash) is None:
            raise ValueError("Memory job execution identity hash is invalid.")
        if self.digest(version) != expected_hash:
            raise ValueError("Memory job execution identity hash does not match.")


class MemoryJobManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instruction_text: StrictStr = Field(min_length=1)
    instruction_version: StrictStr = Field(min_length=1)
    source_turn_ids: tuple[uuid.UUID, ...] = Field(min_length=1)
    source_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    language: StrictStr = Field(min_length=1)

    @field_validator("source_turn_ids", mode="before")
    @classmethod
    def parse_json_source_ids(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(uuid.UUID(item) if isinstance(item, str) else item for item in value)
