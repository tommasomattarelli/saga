from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.generation_errors import Adapter
from app.ai.generation_execution import GenerationProvider, execute_generation
from app.ai.generation_execution_ledger import (
    GenerationLedger,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
)
from app.ai.response_validation import (
    DiagnosticCode,
    ResponseValidationError,
    ValidatedResponse,
    ValidationDiagnostic,
    safe_path,
    validate_response,
)
from app.ai.router import ModelConfig
from app.ai.session_affinity import campaign_session_affinity
from app.memory.document_contracts import GlobalPayload, SummaryPayload
from app.memory.producer_contracts import (
    BatchPayload,
    FactsPayload,
    MemoryOutputError,
    ResolvedFact,
    resolve_facts,
    validate_facts_context,
)
from app.memory.producer_prompts import (
    MemoryPayload,
    PreparedMemoryRequest,
    canonical,
    digest,
    response_contract,
)


class _UseCampaignAffinity:
    pass


_USE_CAMPAIGN_AFFINITY = _UseCampaignAffinity()


@dataclass(frozen=True)
class MemoryGeneration:
    payload: MemoryPayload
    facts: tuple[ResolvedFact, ...]
    provider: str
    model: str
    raw: str
    send_number: int


def build_generation_request(
    prepared: PreparedMemoryRequest,
    config: ModelConfig,
    *,
    session_affinity: str | None | _UseCampaignAffinity = _USE_CAMPAIGN_AFFINITY,
) -> GenerationRequest:
    if isinstance(session_affinity, _UseCampaignAffinity):
        session_affinity = campaign_session_affinity()
    destination = config.destination_fingerprint
    if not destination:
        raise ValueError("A frozen memory request requires a destination fingerprint.")
    effective_schema = prepared.response_schema
    identity = digest(
        canonical(
            {
                "role": prepared.kind,
                "executor_system_prompt": prepared.executor_system_prompt,
                "user_prompt": prepared.user_prompt,
                "source_hash": prepared.source_hash,
                "schema": effective_schema,
                "facts_policy": prepared.facts_policy.model_dump(mode="json"),
                "provider": config.provider,
                "model": config.model,
                "destination": destination,
                "output_limit": config.max_tokens,
                "allow_json_mode_fallback": config.allow_json_mode_fallback,
                "allow_prompt_only_fallback": config.allow_prompt_only_fallback,
                "session_affinity": session_affinity,
            }
        )
    )
    return GenerationRequest.create(
        prepared.executor_system_prompt,
        [{"role": "user", "content": prepared.user_prompt}],
        contract=response_contract(prepared.kind),
        provider=config.provider,
        model=config.model,
        destination_fingerprint=destination,
        role=prepared.kind,
        logical_result_id=identity,
        output_limit=OutputLimit(configured_ceiling=config.max_tokens),
        effective_schema=effective_schema,
        format_mode=FormatMode.STRICT_NATIVE,
        allow_json_mode_fallback=config.allow_json_mode_fallback,
        allow_prompt_only_fallback=config.allow_prompt_only_fallback,
        session_affinity=session_affinity,
        contextual_validator_version=f"memory-context-{prepared.kind}-v1",
    )


def memory_response_validator(
    prepared: PreparedMemoryRequest,
    base_request: GenerationRequest,
) -> Callable[[RawGenerationReceipt, GenerationRequest], ValidatedResponse[MemoryPayload]]:
    def validate(
        receipt: RawGenerationReceipt, current_request: GenerationRequest
    ) -> ValidatedResponse[MemoryPayload]:
        _validate_request_context(prepared, base_request, current_request)
        if receipt.text is None:
            raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),))
        validated = validate_response(receipt.text, current_request.contract)
        payload = validated.model
        if isinstance(payload, FactsPayload):
            try:
                validate_facts_context(payload, prepared.source, prepared.facts_policy)
            except MemoryOutputError as exc:
                diagnostic = ValidationDiagnostic(
                    DiagnosticCode.VALIDATION_FAILED,
                    safe_path(exc.diagnostic_path, current_request.canonical_schema),
                )
                raise ResponseValidationError((diagnostic,), validated.normalization) from None
        expected_type = {
            "batch": BatchPayload,
            "summary": SummaryPayload,
            "facts": FactsPayload,
            "global": GlobalPayload,
        }[prepared.kind]
        if not isinstance(payload, expected_type):
            raise ValueError("Memory response contract returned an unexpected payload type.")
        return cast(ValidatedResponse[MemoryPayload], validated)

    return validate


def _validate_request_context(
    prepared: PreparedMemoryRequest,
    base_request: GenerationRequest,
    current_request: GenerationRequest,
) -> None:
    base_messages = base_request.messages
    current_messages = current_request.messages
    if (
        current_request.system_prompt != prepared.executor_system_prompt
        or current_request.role != prepared.kind
        or current_request.logical_result_id != base_request.logical_result_id
        or current_request.contract.name != response_contract(prepared.kind).name
        or current_request.contract.version != response_contract(prepared.kind).version
        or current_request.contract.schema_hash != response_contract(prepared.kind).schema_hash
        or current_request.canonical_schema != prepared.response_schema
        or current_request.wire_schema != base_request.wire_schema
        or current_request.wire_encoding_version != base_request.wire_encoding_version
        or current_request.contextual_validator_version
        != base_request.contextual_validator_version
        or current_request.provider != base_request.provider
        or current_request.model != base_request.model
        or current_request.destination_fingerprint != base_request.destination_fingerprint
        or current_request.output_limit != base_request.output_limit
        or current_request.tool_declarations != base_request.tool_declarations
        or current_request.session_affinity != base_request.session_affinity
        or current_request.allow_json_mode_fallback != base_request.allow_json_mode_fallback
        or current_request.allow_prompt_only_fallback != base_request.allow_prompt_only_fallback
        or not base_messages
        or not current_messages
        or current_messages[0] != base_messages[0]
    ):
        raise ValueError("Memory generation request identity changed.")


async def execute_memory_generation(
    prepared: PreparedMemoryRequest,
    *,
    provider: GenerationProvider,
    ledger: GenerationLedger,
    config: ModelConfig,
    policy: GenerationRecoveryPolicy,
    adapter: Adapter,
    session_affinity: str | None | _UseCampaignAffinity = _USE_CAMPAIGN_AFFINITY,
) -> MemoryGeneration:
    base = build_generation_request(prepared, config, session_affinity=session_affinity)
    result = await execute_generation(
        base,
        provider,
        ledger,
        policy,
        adapter,
        validator=memory_response_validator(prepared, base),
    )
    payload = result.value
    facts = resolve_facts(payload, prepared.source) if isinstance(payload, FactsPayload) else ()
    successful = next(
        (
            outcome
            for outcome in reversed(result.sends)
            if outcome.status is GenerationOutcomeStatus.VALID
        ),
        None,
    )
    if (
        successful is None
        or successful.receipt is None
        or successful.receipt.raw_candidate is None
    ):
        raise RuntimeError("Successful memory generation did not retain its raw candidate.")
    return MemoryGeneration(
        payload=payload,
        facts=facts,
        provider=config.provider,
        model=config.model,
        raw=successful.receipt.raw_candidate,
        send_number=successful.reservation.number,
    )
