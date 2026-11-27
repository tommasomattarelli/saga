from __future__ import annotations

import hashlib
import json
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import (
    GenerationExecutionResult,
    GenerationProvider,
    execute_generation,
)
from app.ai.generation_execution_ledger import (
    GenerationLedger,
    GenerationRecoveryPolicy,
)
from app.ai.response_contracts import ResponseContract, parse_json_document
from app.ai.response_validation import (
    DiagnosticCode,
    Normalization,
    ResponseValidationError,
    ValidatedResponse,
    ValidationDiagnostic,
    validate_response,
    validation_diagnostics,
)
from app.ai.router import ModelConfig
from app.ai.tools.dm_tools import get_tool
from app.ai.tools.tools_npc import UpdateNpc
from app.ai.tools.tools_world import ChangeNpcPsychology
from app.ai.wire_contracts import decode_wire, wire_model_for


class DMNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str | None


DM_NARRATIVE_CONTRACT = ResponseContract("dm-narrative", "v1", DMNarrative)


def build_dm_generation_request(
    system_prompt: str,
    messages: list[dict[str, object]],
    *,
    config: ModelConfig,
    allowed_tools: set[str],
    campaign_id: str,
    player_action: str,
    step: int,
    previous_head_turn_id: str | None,
    session_affinity: str | None,
    taxonomy: dict | None = None,
) -> GenerationRequest:
    destination = config.destination_fingerprint
    if not destination:
        raise ValueError("A DM generation request requires a destination fingerprint.")
    logical_result_id = hashlib.sha256(
        json.dumps(
            {
                "campaign_id": campaign_id,
                "previous_head_turn_id": previous_head_turn_id,
                "player_action": player_action,
                "step": step,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    declarations = generation_tool_declarations(allowed_tools, taxonomy)
    return GenerationRequest.create(
        system_prompt,
        messages,
        contract=DM_NARRATIVE_CONTRACT,
        provider=config.provider,
        model=config.model,
        destination_fingerprint=destination,
        role="dm",
        logical_result_id=logical_result_id,
        output_limit=OutputLimit(configured_ceiling=config.max_tokens),
        tool_declarations=declarations,
        format_mode=FormatMode.PROMPT_ONLY if declarations else FormatMode.STRICT_NATIVE,
        allow_json_mode_fallback=config.allow_json_mode_fallback,
        allow_prompt_only_fallback=config.allow_prompt_only_fallback,
        session_affinity=session_affinity,
        contextual_validator_version="dm-narrative-v1",
    )


def generation_tool_declarations(
    allowed_tools: set[str], taxonomy: dict | None = None
) -> list[dict[str, object]]:
    return [
        tool.to_generation_schema(taxonomy)
        for name in sorted(allowed_tools)
        if (tool := get_tool(name)) is not None
    ]


def validate_dm_narrative(
    receipt: RawGenerationReceipt,
    *,
    allow_plain_prose: bool = False,
) -> ValidatedResponse[DMNarrative]:
    if receipt.text is None or not receipt.text.strip():
        if receipt.tool_calls:
            return ValidatedResponse(DMNarrative(text=None), Normalization.NONE)
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.MISSING, ("text",)),))

    try:
        result = validate_response(receipt.text, DM_NARRATIVE_CONTRACT)
    except ResponseValidationError as error:
        if (
            not allow_plain_prose
            or not any(item.code == DiagnosticCode.INVALID_JSON for item in error.diagnostics)
            or error.normalization is not Normalization.NONE
            or receipt.text.lstrip().startswith(("{", "["))
        ):
            raise
        result = ValidatedResponse(DMNarrative(text=receipt.text.strip()), Normalization.NONE)
    if not receipt.tool_calls and not (result.model.text or "").strip():
        raise ResponseValidationError(
            (ValidationDiagnostic(DiagnosticCode.MISSING, ("text",)),),
            result.normalization,
        )
    return result


def dm_response_validator(
    receipt: RawGenerationReceipt, request: GenerationRequest
) -> ValidatedResponse[DMNarrative]:
    if (
        request.contract.name != DM_NARRATIVE_CONTRACT.name
        or request.contract.version != DM_NARRATIVE_CONTRACT.version
        or request.contract.schema_hash != DM_NARRATIVE_CONTRACT.schema_hash
    ):
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),))
    validated = validate_dm_narrative(
        receipt,
        allow_plain_prose=(
            request.format_mode is FormatMode.PROMPT_ONLY and bool(request.tool_declarations)
        ),
    )
    for call in receipt.tool_calls:
        canonical_tool_arguments(call, request)
    return validated


def canonical_tool_arguments(
    call: GenerationToolReceipt, request: GenerationRequest
) -> dict[str, object]:
    selected = _selected_tool_names(request)
    if call.name is None or (tool := get_tool(call.name)) is None:
        raise ResponseValidationError(
            (ValidationDiagnostic(DiagnosticCode.TOOL_NOT_REGISTERED, ()),)
        )
    if call.name not in selected:
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.TOOL_UNAVAILABLE, ()),))

    if call.arguments.kind == "raw_text":
        raw = call.arguments.raw_text_value
        try:
            payload = parse_json_document(raw) if raw is not None else None
        except (TypeError, ValueError):
            raise ResponseValidationError(
                (ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),)
            ) from None
    else:
        payload = call.arguments.structured_value

    if not isinstance(payload, dict):
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.EXPECTED_OBJECT, ()),))

    if tool is UpdateNpc or tool is ChangeNpcPsychology:
        wire_model = wire_model_for(tool)
        try:
            wire_model.model_validate(payload, strict=True)
        except ValidationError as error:
            raise ResponseValidationError(
                validation_diagnostics(error, wire_model.model_json_schema())
            ) from None
        try:
            canonical = decode_wire(tool, payload)
        except ValidationError as error:
            raise ResponseValidationError(
                validation_diagnostics(error, tool.model_json_schema())
            ) from None
    else:
        try:
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
            canonical = tool.model_validate_json(encoded, strict=True)
        except ValidationError as error:
            raise ResponseValidationError(
                validation_diagnostics(error, tool.model_json_schema())
            ) from None
        except (TypeError, ValueError):
            raise ResponseValidationError(
                (ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),)
            ) from None

    canonical_arguments = cast(dict[str, object], canonical.model_dump(mode="json"))
    return {name: canonical_arguments[name] for name in cast(dict[str, object], payload)}


def _selected_tool_names(request: GenerationRequest) -> set[str]:
    selected: set[str] = set()
    for declaration in request.tool_declarations:
        function = declaration.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str):
                selected.add(name)
    return selected


async def execute_dm_generation(
    request: GenerationRequest,
    provider: GenerationProvider,
    ledger: GenerationLedger,
    policy: GenerationRecoveryPolicy,
    adapter: Adapter,
) -> GenerationExecutionResult[DMNarrative]:
    return await execute_generation(
        request,
        provider,
        ledger,
        policy,
        adapter,
        validator=dm_response_validator,
    )
