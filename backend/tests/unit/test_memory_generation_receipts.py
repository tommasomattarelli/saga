import base64

import pytest

from app.ai.generation_contracts import (
    FormatMode,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.providers.usage import UsageMetadata
from app.memory.generation_receipts import decode_receipt, encode_receipt


def test_raw_receipt_round_trips_without_candidate_duplication() -> None:
    receipt = RawGenerationReceipt(
        text="text",
        tool_calls=(
            GenerationToolReceipt(
                call_id="call-1",
                name="tool",
                arguments=RawToolArguments.raw_text('{"not": valid}'),
                signature=b"\x00tool-signature",
            ),
            GenerationToolReceipt(
                call_id="call-2",
                name="structured",
                arguments=RawToolArguments.structured({"x": [1, True]}),
            ),
        ),
        finish_reason="stop",
        refusal="refusal",
        blocked_reason="blocked",
        response_id="response",
        model_id="model",
        usage=UsageMetadata(
            response_id="usage-response",
            model="usage-model",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            cached_input_tokens=4,
            reasoning_output_tokens=5,
            cost=0.25,
            currency="USD",
        ),
        text_signature=b"\xfftext-signature",
        raw_candidate="model-output-only-987",
    )

    encoded, candidate = encode_receipt(receipt)

    assert candidate == receipt.raw_candidate
    assert receipt.raw_candidate is not None
    assert receipt.raw_candidate not in encoded
    assert decode_receipt(encoded, candidate) == receipt
    assert base64.b64encode(b"\xfftext-signature").decode() in encoded


@pytest.mark.parametrize(
    "encoded",
    [
        "{}",
        '{"encoding_version":99,"receipt":{}}',
        '{"encoding_version":1,"receipt":{},"unknown":true}',
    ],
)
def test_receipt_decoder_rejects_unknown_or_malformed_envelopes(encoded: str) -> None:
    with pytest.raises(ValueError):
        decode_receipt(encoded, None)


def test_identity_snapshot_serializer_is_canonical_with_unicode_and_integer_limits() -> None:
    from app.memory.job_contracts import (
        MemoryGenerationRequestIdentitySnapshot,
        MemoryOutputLimitSnapshot,
    )

    snapshot = MemoryGenerationRequestIdentitySnapshot(
        format_version=1,
        role="summary",
        logical_result_id="café/β",
        initial_prefix_hash="a" * 64,
        contract_name="memo",
        contract_version="v1",
        contract_schema_hash="b" * 64,
        effective_schema_hash="c" * 64,
        wire_encoding_version="wire-v1",
        wire_schema_hash="d" * 64,
        tool_declarations_hash="e" * 64,
        contextual_validator_version="ctx-v1",
        provider="local",
        model="mødel/β",
        destination_fingerprint="f" * 64,
        output_limit=MemoryOutputLimitSnapshot(
            configured_ceiling=60000, known_lower_limit=None, limit_source=None
        ),
        format_mode=FormatMode.STRICT_NATIVE,
        allow_json_mode_fallback=False,
        allow_prompt_only_fallback=False,
        session_affinity=None,
    )
    assert snapshot.snapshot_json == (
        '{"allow_json_mode_fallback":false,"allow_prompt_only_fallback":false,'
        '"contextual_validator_version":"ctx-v1","contract_name":"memo",'
        '"contract_schema_hash":"' + "b" * 64 + '","contract_version":"v1",'
        '"destination_fingerprint":"'
        + "f" * 64
        + '","effective_schema_hash":"'
        + "c" * 64
        + '","format_mode":"strict_native","format_version":1,"initial_prefix_hash":"'
        + "a" * 64
        + '","logical_result_id":"café/β","model":"mødel/β",'
        '"output_limit":{"configured_ceiling":60000,"known_lower_limit":null,'
        '"limit_source":null},"provider":"local","role":"summary","session_affinity":null,'
        '"tool_declarations_hash":"'
        + "e" * 64
        + '","wire_encoding_version":"wire-v1","wire_schema_hash":"'
        + "d" * 64
        + '"}'
    )
