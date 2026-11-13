from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Literal, cast

from pydantic import BaseModel, JsonValue

from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.providers.usage import UsageMetadata
from app.ai.response_contracts import ResponseContract


def _copy_json(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return cast(JsonValue, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Generation snapshots require finite numbers.")
        return value
    if isinstance(value, bytes):
        raise TypeError("Generation snapshots require JSON values.")
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Generation snapshot object keys must be strings.")
        copied: dict[str, JsonValue] = {}
        for key, item in value.items():
            copied[key] = _copy_json(item)
        return copied
    raise TypeError("Unsupported generation snapshot value.")


def _snapshot_messages(messages: list[dict[str, object]]) -> str:
    encoded: list[JsonValue] = []
    for message in messages:
        ordinary = dict(message)
        for key in (TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY):
            if isinstance(message.get(key), bytes) or (
                key == TOOL_CALL_SIGNATURES_KEY and isinstance(message.get(key), dict)
            ):
                ordinary.pop(key)
        copied = cast(dict[str, JsonValue], _copy_json(ordinary))
        signatures: dict[str, JsonValue] = {}
        for key in (TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY):
            value = message.get(key)
            if key == TEXT_SIGNATURE_KEY and isinstance(value, bytes):
                copied.pop(key, None)
                signatures[key] = {
                    "encoding_version": 1,
                    "base64": base64.b64encode(value).decode("ascii"),
                }
            elif key == TOOL_CALL_SIGNATURES_KEY and isinstance(value, dict):
                copied_values: dict[str, JsonValue] = {}
                byte_values: list[str] = []
                for signature_id, signature in value.items():
                    if not isinstance(signature_id, str):
                        raise TypeError("Generation signature IDs must be strings.")
                    if isinstance(signature, bytes):
                        copied_values[signature_id] = {
                            "encoding_version": 1,
                            "base64": base64.b64encode(signature).decode("ascii"),
                        }
                        byte_values.append(signature_id)
                    else:
                        copied_values[signature_id] = _copy_json(signature)
                copied.pop(key, None)
                signatures[key] = {
                    "values": copied_values,
                    "byte_values": cast(list[JsonValue], byte_values),
                }
        encoded.append(
            {
                "encoding_version": 1,
                "message": copied,
                "signatures": signatures,
            }
        )
    return _canonical_json(encoded)


def _restore_signature(value: JsonValue) -> bytes:
    if not isinstance(value, dict) or value.get("encoding_version") != 1:
        raise ValueError("Invalid generation snapshot signature.")
    encoded = value.get("base64")
    if set(value) != {"encoding_version", "base64"} or not isinstance(encoded, str):
        raise ValueError("Invalid generation snapshot signature.")
    return base64.b64decode(encoded, validate=True)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class GenerationRequest:
    system_prompt: str
    _messages_json: str = field(repr=False)
    contract: ResponseContract[BaseModel]
    provider: str
    model: str
    destination_fingerprint: str
    role: str
    logical_result_id: str
    output_limit: OutputLimit
    format_mode: FormatMode
    allow_json_mode_fallback: bool
    allow_prompt_only_fallback: bool
    session_affinity: str | None
    contextual_validator_version: str
    wire_encoding_version: str
    _tools_json: str = field(default="[]", repr=False)
    _wire_schema_json: str = field(default="", repr=False)
    _effective_schema_json: str = field(default="", repr=False)

    @classmethod
    def create(
        cls,
        system_prompt: str,
        messages: list[dict[str, object]],
        *,
        contract: ResponseContract[BaseModel],
        provider: str,
        model: str,
        destination_fingerprint: str,
        role: str,
        logical_result_id: str,
        output_limit: OutputLimit,
        tool_declarations: list[dict[str, object]] | None = None,
        wire_model: type[BaseModel] | None = None,
        effective_schema: dict[str, JsonValue] | None = None,
        format_mode: FormatMode | None = None,
        allow_json_mode_fallback: bool = False,
        allow_prompt_only_fallback: bool = False,
        session_affinity: str | None = None,
        contextual_validator_version: str = "context-v1",
        wire_encoding_version: str = "wire-v1",
    ) -> GenerationRequest:
        snapshot = _snapshot_messages(messages)
        tools_json = _canonical_json(
            _copy_json([] if tool_declarations is None else tool_declarations)
        )
        selected_wire_model = wire_model or contract.model_type
        wire_schema_json = _canonical_json(selected_wire_model.model_json_schema())
        selected_schema = contract.schema if effective_schema is None else effective_schema
        effective_schema_json = _canonical_json(selected_schema)
        return cls(
            system_prompt=system_prompt,
            _messages_json=snapshot,
            contract=contract,
            provider=provider,
            model=model,
            destination_fingerprint=destination_fingerprint,
            role=role,
            logical_result_id=logical_result_id,
            output_limit=output_limit,
            format_mode=FormatMode.STRICT_NATIVE if format_mode is None else format_mode,
            allow_json_mode_fallback=allow_json_mode_fallback,
            allow_prompt_only_fallback=allow_prompt_only_fallback,
            session_affinity=session_affinity,
            contextual_validator_version=contextual_validator_version,
            wire_encoding_version=wire_encoding_version,
            _tools_json=tools_json,
            _wire_schema_json=wire_schema_json,
            _effective_schema_json=effective_schema_json,
        )

    @property
    def identity(self) -> GenerationIdentity:
        return GenerationIdentity.create(
            contract=self.contract,
            role=self.role,
            logical_result_id=self.logical_result_id,
            initial_prefix_hash=self.initial_prefix_hash,
            wire_schema=self.wire_schema,
            effective_schema=self.canonical_schema,
            tool_declarations=self.tool_declarations,
            wire_encoding_version=self.wire_encoding_version,
            contextual_validator_version=self.contextual_validator_version,
            provider=self.provider,
            model=self.model,
            destination_fingerprint=self.destination_fingerprint,
            output_limit=self.output_limit,
            format_mode=self.format_mode,
            allow_json_mode_fallback=self.allow_json_mode_fallback,
            allow_prompt_only_fallback=self.allow_prompt_only_fallback,
            session_affinity=self.session_affinity,
        )

    @property
    def initial_prefix_hash(self) -> str:
        return hashlib.sha256(
            _canonical_json(
                {"system_prompt": self.system_prompt, "messages": json.loads(self._messages_json)}
            ).encode()
        ).hexdigest()

    @property
    def tool_declarations(self) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], json.loads(self._tools_json))

    @property
    def wire_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._wire_schema_json))

    @property
    def canonical_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._effective_schema_json))

    @property
    def messages(self) -> list[dict[str, object]]:
        entries = cast(list[dict[str, JsonValue]], json.loads(self._messages_json))
        decoded: list[dict[str, object]] = []
        for entry in entries:
            message = cast(dict[str, object], entry["message"])
            signatures = cast(dict[str, JsonValue], entry.get("signatures", {}))
            for key, value in signatures.items():
                if key == TEXT_SIGNATURE_KEY:
                    message[key] = _restore_signature(value)
            tool_sidechannel = signatures.get(TOOL_CALL_SIGNATURES_KEY)
            if isinstance(tool_sidechannel, dict):
                values = cast(dict[str, JsonValue], tool_sidechannel["values"])
                byte_values = cast(list[str], tool_sidechannel["byte_values"])
                message[TOOL_CALL_SIGNATURES_KEY] = {
                    name: _restore_signature(value) if name in byte_values else value
                    for name, value in values.items()
                }
            decoded.append(message)
        return decoded

    @property
    def snapshot_json(self) -> str:
        return _canonical_json(
            {
                "encoding_version": 1,
                "system_prompt": self.system_prompt,
                "messages": json.loads(self._messages_json),
            }
        )


class FormatMode(StrEnum):
    STRICT_NATIVE = "strict_native"
    JSON_MODE = "json_mode"
    PROMPT_ONLY = "prompt_only"


@dataclass(frozen=True)
class OutputLimit:
    configured_ceiling: int
    known_lower_limit: int | None = None
    limit_source: str | None = None

    def __post_init__(self) -> None:
        if self.configured_ceiling <= 0:
            raise ValueError("Configured output ceiling must be positive.")
        if self.known_lower_limit is not None:
            if self.known_lower_limit <= 0:
                raise ValueError("Known model output limit must be positive.")
            if not self.limit_source:
                raise ValueError("A known lower output limit requires its source.")
        elif self.limit_source is not None:
            raise ValueError("A limit source requires a known lower output limit.")

    @property
    def effective(self) -> int:
        return min(self.configured_ceiling, self.known_lower_limit or self.configured_ceiling)


@dataclass(frozen=True)
class GenerationIdentity:
    format_version: int
    role: str
    logical_result_id: str
    initial_prefix_hash: str
    contract_name: str
    contract_version: str
    contract_schema_hash: str
    effective_schema_hash: str
    wire_encoding_version: str
    wire_schema_hash: str
    tool_declarations_hash: str
    contextual_validator_version: str
    provider: str
    model: str
    destination_fingerprint: str
    output_limit: OutputLimit
    format_mode: FormatMode
    allow_json_mode_fallback: bool
    allow_prompt_only_fallback: bool
    session_affinity: str | None

    @property
    def snapshot_json(self) -> str:
        return _canonical_json(asdict(self))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.snapshot_json.encode()).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        contract: ResponseContract[BaseModel],
        role: str,
        logical_result_id: str,
        initial_prefix_hash: str,
        wire_model: type[BaseModel] | None = None,
        wire_schema: dict[str, JsonValue] | None = None,
        effective_schema: dict[str, JsonValue] | None = None,
        tool_declarations: list[dict[str, object]] | None = None,
        wire_encoding_version: str = "wire-v1",
        contextual_validator_version: str,
        provider: str,
        model: str,
        destination_fingerprint: str,
        output_limit: OutputLimit,
        format_mode: FormatMode,
        allow_json_mode_fallback: bool,
        allow_prompt_only_fallback: bool,
        session_affinity: str | None = None,
    ) -> GenerationIdentity:
        selected_wire_schema = (
            wire_model.model_json_schema()
            if wire_schema is None and wire_model is not None
            else wire_schema
        )
        if selected_wire_schema is None:
            raise ValueError("A wire schema or model is required.")
        wire_schema_json = _canonical_json(selected_wire_schema)
        wire_hash = hashlib.sha256(wire_schema_json.encode()).hexdigest()
        tools_hash = hashlib.sha256(
            _canonical_json(_copy_json(tool_declarations or [])).encode()
        ).hexdigest()
        effective_hash = hashlib.sha256(
            _canonical_json(
                contract.schema if effective_schema is None else effective_schema
            ).encode()
        ).hexdigest()
        return cls(
            format_version=1,
            role=role,
            logical_result_id=logical_result_id,
            initial_prefix_hash=initial_prefix_hash,
            contract_name=contract.name,
            contract_version=contract.version,
            contract_schema_hash=contract.schema_hash,
            effective_schema_hash=effective_hash,
            wire_encoding_version=wire_encoding_version,
            wire_schema_hash=wire_hash,
            tool_declarations_hash=tools_hash,
            contextual_validator_version=contextual_validator_version,
            provider=provider,
            model=model,
            destination_fingerprint=destination_fingerprint,
            output_limit=output_limit,
            format_mode=format_mode,
            allow_json_mode_fallback=allow_json_mode_fallback,
            allow_prompt_only_fallback=allow_prompt_only_fallback,
            session_affinity=session_affinity,
        )


@dataclass(frozen=True)
class RawToolArguments:
    kind: Literal["raw_text", "structured"]
    raw_text_value: str | None = None
    _structured_json: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.kind == "raw_text":
            valid = self.raw_text_value is not None and self._structured_json is None
        else:
            valid = self.raw_text_value is None and self._structured_json is not None
        if not valid:
            raise ValueError("Tool arguments must contain exactly one representation.")

    @classmethod
    def raw_text(cls, value: str) -> RawToolArguments:
        return cls("raw_text", raw_text_value=value)

    @classmethod
    def structured(cls, value: object) -> RawToolArguments:
        copied = _copy_json(value)
        return cls("structured", _structured_json=_canonical_json(copied))

    @property
    def structured_value(self) -> JsonValue | None:
        if self._structured_json is None:
            return None
        return cast(JsonValue, json.loads(self._structured_json))


@dataclass(frozen=True)
class GenerationToolReceipt:
    call_id: str | None
    name: str | None
    arguments: RawToolArguments
    signature: bytes | None = None


@dataclass(frozen=True)
class RawGenerationReceipt:
    text: str | None
    tool_calls: tuple[GenerationToolReceipt, ...] = ()
    finish_reason: str | None = None
    refusal: str | None = None
    blocked_reason: str | None = None
    response_id: str | None = None
    model_id: str | None = None
    usage: UsageMetadata | None = None
    text_signature: bytes | None = None
    raw_candidate: str | None = None
