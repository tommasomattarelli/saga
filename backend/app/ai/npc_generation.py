from __future__ import annotations

import json
from collections.abc import Mapping
from copy import copy
from functools import lru_cache
from types import GenericAlias
from typing import cast, get_args, get_origin

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
)
from pydantic.fields import FieldInfo

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.npc_outcomes import (
    NPC_RESPONSE_CONTRACT,
    NPCResponse,
    npc_response_schema,
    validate_actor_response,
)
from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    ResponseValidationError,
    ValidatedResponse,
    ValidationDiagnostic,
    validate_response,
    validation_diagnostics,
)
from app.ai.router import ModelConfig
from app.ai.session_affinity import campaign_session_affinity
from app.core.psychology import DEFAULT_PSYCHOLOGY
from app.models.psychology import PsychologyDef

_NPC_CONTEXT_VERSION = "npc-context-v1"
_NPC_WIRE_VERSION = "npc-axis-entries-v1"


@lru_cache(maxsize=32)
def _wire_contract(axis_names: tuple[str, ...]) -> ResponseContract[BaseModel]:
    source_field = NPCResponse.model_fields["axis_changes"]
    annotation = source_field.annotation
    if get_origin(annotation) is not dict:
        raise TypeError("NPCResponse.axis_changes must remain a dictionary contract.")
    key_type, value_type = get_args(annotation)
    if not isinstance(key_type, type):
        raise TypeError("NPCResponse.axis_changes requires a typed key.")
    entry = create_model(
        "NPCAxisChangeEntry",
        __config__=ConfigDict(extra="forbid", strict=True),
        key=(key_type, Field(..., json_schema_extra={"enum": list(axis_names)})),
        value=(value_type, ...),
    )

    def reject_duplicate_keys(entries: list[BaseModel]) -> list[BaseModel]:
        keys = [cast(str, item.model_dump()["key"]) for item in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate axis entry.")
        return entries

    fields: dict[str, tuple[object, FieldInfo]] = {}
    for name, source in NPCResponse.model_fields.items():
        if name == "axis_changes":
            fields[name] = (GenericAlias(list, entry), copy(source_field))
            fields[name][1].default = ...
            fields[name][1].default_factory = None
        else:
            field = copy(source)
            field.default = ...
            field.default_factory = None
            fields[name] = (source.annotation, field)
    wire = create_model(
        "NPCResponseWire",
        __config__=ConfigDict(extra="forbid", strict=True),
        __validators__={
            "unique_axis_entries": field_validator("axis_changes")(reject_duplicate_keys)
        },
        **fields,
    )  # type: ignore[call-overload]
    return cast(
        ResponseContract[BaseModel],
        ResponseContract("npc_actor_wire", _NPC_WIRE_VERSION, wire),
    )


def build_npc_generation_request(
    *,
    system_prompt: str,
    prompt: str,
    config: ModelConfig,
    logical_result_id: str,
    psychology: PsychologyDef | None,
    session_affinity: str | None = None,
) -> GenerationRequest:
    destination = config.destination_fingerprint
    if not destination:
        raise ValueError("NPC generation requires a resolved destination fingerprint.")
    axis_names = tuple(sorted((psychology or DEFAULT_PSYCHOLOGY).axes))
    return GenerationRequest.create(
        system_prompt,
        [{"role": "user", "content": prompt}],
        contract=NPC_RESPONSE_CONTRACT,
        provider=config.provider,
        model=config.model,
        destination_fingerprint=destination,
        role="actor",
        logical_result_id=logical_result_id,
        output_limit=OutputLimit(configured_ceiling=config.max_tokens),
        wire_schema=_wire_contract(axis_names).schema,
        effective_schema=npc_response_schema(psychology),
        format_mode=FormatMode.STRICT_NATIVE,
        allow_json_mode_fallback=config.allow_json_mode_fallback,
        allow_prompt_only_fallback=config.allow_prompt_only_fallback,
        session_affinity=(
            campaign_session_affinity() if session_affinity is None else session_affinity
        ),
        contextual_validator_version=_NPC_CONTEXT_VERSION,
        wire_encoding_version=_NPC_WIRE_VERSION,
    )


def validate_npc_response(
    receipt: RawGenerationReceipt,
    request: GenerationRequest,
    *,
    max_lines: int,
    psychology: PsychologyDef | None,
) -> ValidatedResponse[NPCResponse]:
    axis_names = _axis_names_from_schema(request.canonical_schema)
    if (
        request.contract.name != NPC_RESPONSE_CONTRACT.name
        or request.contract.version != NPC_RESPONSE_CONTRACT.version
        or request.contract.schema_hash != NPC_RESPONSE_CONTRACT.schema_hash
        or request.canonical_schema != npc_response_schema(psychology)
        or request.wire_schema != _wire_contract(axis_names).schema
        or request.contextual_validator_version != _NPC_CONTEXT_VERSION
        or request.wire_encoding_version != _NPC_WIRE_VERSION
    ):
        raise ResponseValidationError(
            (ValidationDiagnostic(DiagnosticCode.VALIDATION_FAILED, ()),)
        )
    if receipt.text is None:
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),))

    if request.format_mode is FormatMode.STRICT_NATIVE:
        validated_wire = validate_response(receipt.text, _wire_contract(axis_names))
        wire_data = validated_wire.model.model_dump(mode="python")
        entries = cast(list[dict[str, object]], wire_data["axis_changes"])
        wire_data["axis_changes"] = {cast(str, item["key"]): item["value"] for item in entries}
        raw_canonical = json.dumps(wire_data, ensure_ascii=False, allow_nan=False)
        normalization = validated_wire.normalization
        try:
            canonical = NPC_RESPONSE_CONTRACT.validate(raw_canonical)
        except ValidationError as error:
            raise ResponseValidationError(
                validation_diagnostics(error, NPC_RESPONSE_CONTRACT.schema),
                normalization,
            ) from None
    else:
        validated_canonical = validate_response(receipt.text, NPC_RESPONSE_CONTRACT)
        canonical = validated_canonical.model
        normalization = validated_canonical.normalization
    try:
        validate_actor_response(canonical, max_lines, psychology, axis_names)
    except ResponseValidationError as error:
        diagnostics = error.diagnostics
        if any(
            diagnostic.code is DiagnosticCode.INVALID_ENUM and diagnostic.path == ("axis_changes",)
            for diagnostic in diagnostics
        ):
            if request.format_mode is FormatMode.STRICT_NATIVE:
                entry_index = next(
                    index
                    for index, axis in enumerate(canonical.axis_changes)
                    if axis not in axis_names
                )
                contextual_path: tuple[str | int, ...] = (
                    "axis_changes",
                    entry_index,
                    "key",
                )
            else:
                contextual_path = ("axis_changes",)
            diagnostics = tuple(
                ValidationDiagnostic(diagnostic.code, contextual_path)
                if diagnostic.code is DiagnosticCode.INVALID_ENUM
                and diagnostic.path == ("axis_changes",)
                else diagnostic
                for diagnostic in diagnostics
            )
        raise ResponseValidationError(diagnostics, normalization) from None
    return ValidatedResponse(canonical, normalization)


def _axis_names_from_schema(schema: Mapping[str, object]) -> tuple[str, ...]:
    properties = cast(dict[str, object], schema["properties"])
    axis_changes = cast(dict[str, object], properties["axis_changes"])
    axes = cast(dict[str, object], axis_changes["properties"])
    return tuple(axes)
