import json

import pytest

from app.ai.router import ModelConfig
from app.memory.producer_prompts import ProducerKind
from app.memory.production_policy import GlobalPolicy
from tests.unit.test_memory_producers import request


def test_memory_receipt_validator_accepts_each_real_contract() -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.memory.document_contracts import GlobalPayload, SummaryPayload
    from app.memory.producer_contracts import BatchPayload, FactsPayload
    from app.memory.producers import build_generation_request, memory_response_validator

    config = ModelConfig(
        provider="local",
        model="unit-model",
        max_tokens=731,
        destination_fingerprint="destination-hmac",
    )
    outputs: dict[ProducerKind, str] = {
        "summary": '{"text":"Mira hid the key."}',
        "facts": (
            '{"facts":[{"content":"Mira hid the key.","category":"information",'
            '"assertion_type":"occurrence","entities":[],"attribution":[],"source_turns":["t1"],'
            '"temporal_references":[],"importance":{"level":"major","reason":"A key matters."}}]}'
        ),
        "batch": (
            '{"summary":{"text":"Mira hid the key."},"facts":[{"content":"Mira hid the key.",'
            '"category":"information","assertion_type":"occurrence","entities":[],"attribution":[],'
            '"source_turns":["t1"],"temporal_references":[],"importance":{"level":"major",'
            '"reason":"A key matters."}}]}'
        ),
        "global": (
            '{"story_so_far":"The party reached the city.","open_threads":[],"relationships":[],'
            '"resolved_threads":[]}'
        ),
    }
    expected_types = {
        "summary": SummaryPayload,
        "facts": FactsPayload,
        "batch": BatchPayload,
        "global": GlobalPayload,
    }

    for kind, raw in outputs.items():
        prepared = (
            request(kind, global_policy=GlobalPolicy(target_words=200))
            if kind == "global"
            else request(kind)
        )
        generation_request = build_generation_request(prepared, config)
        validated = memory_response_validator(prepared, generation_request)(
            RawGenerationReceipt(text=raw), generation_request
        )
        assert isinstance(validated.model, expected_types[kind])


def test_memory_receipt_validator_accepts_cumulative_correction_derivation() -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.memory.document_contracts import SummaryPayload
    from app.memory.producers import build_generation_request, memory_response_validator

    prepared = request("summary")
    generation_request = build_generation_request(
        prepared,
        ModelConfig(
            provider="local",
            model="unit-model",
            max_tokens=731,
            destination_fingerprint="destination-hmac",
        ),
    )
    derived = generation_request.derive(
        messages=generation_request.messages + [{"role": "user", "content": "Correction request."}]
    )

    validated = memory_response_validator(prepared, generation_request)(
        RawGenerationReceipt(text='{"text":"A corrected summary."}'), derived
    )

    assert isinstance(validated.model, SummaryPayload)
    assert validated.model.text == "A corrected summary."


def test_memory_receipt_validator_rejects_changed_frozen_source_prefix() -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.memory.producers import build_generation_request, memory_response_validator

    prepared = request("summary")
    generation_request = build_generation_request(
        prepared,
        ModelConfig(
            provider="local",
            model="unit-model",
            max_tokens=731,
            destination_fingerprint="destination-hmac",
        ),
    )
    changed = generation_request.derive(
        messages=[
            {"role": "user", "content": "changed source evidence"},
            *generation_request.messages[1:],
        ]
    )

    with pytest.raises(ValueError, match="identity changed"):
        memory_response_validator(prepared, generation_request)(
            RawGenerationReceipt(text='{"text":"Not accepted."}'), changed
        )


@pytest.mark.parametrize(
    ("field", "value", "path"),
    [
        ("source_turns", ["t999"], ("facts", 0, "source_turns")),
        (
            "importance",
            {"level": "unlisted", "reason": "A key matters."},
            ("facts", 0, "importance", "level"),
        ),
    ],
)
def test_memory_receipt_validator_rejects_context_failures_with_safe_diagnostics(
    field: str, value: object, path: tuple[str | int, ...]
) -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.ai.response_validation import ResponseValidationError
    from app.memory.producer_contracts import MemoryOutputError
    from app.memory.producers import build_generation_request, memory_response_validator

    fact: dict[str, object] = {
        "content": "Mira hid the key.",
        "category": "information",
        "assertion_type": "occurrence",
        "entities": [],
        "attribution": [],
        "source_turns": ["t1"],
        "temporal_references": [],
        "importance": {"level": "major", "reason": "A key matters."},
    }
    fact[field] = value
    raw = json.dumps({"facts": [fact]})
    prepared = request("facts")
    generation_request = build_generation_request(
        prepared,
        ModelConfig(
            provider="local",
            model="unit-model",
            max_tokens=731,
            destination_fingerprint="destination-hmac",
        ),
    )

    with pytest.raises(ResponseValidationError) as captured:
        memory_response_validator(prepared, generation_request)(
            RawGenerationReceipt(text=raw), generation_request
        )

    diagnostic = captured.value.diagnostics[0]
    assert diagnostic.path == path
    assert diagnostic.code.value == "validation_failed"
    assert raw not in str(captured.value)
    assert not isinstance(captured.value.__cause__, MemoryOutputError)


def test_memory_receipt_validator_never_exposes_raw_receipt_diagnostics() -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.ai.response_validation import ResponseValidationError
    from app.memory.producers import build_generation_request, memory_response_validator

    prepared = request("summary")
    generation_request = build_generation_request(
        prepared,
        ModelConfig(
            provider="local",
            model="unit-model",
            max_tokens=731,
            destination_fingerprint="destination-hmac",
        ),
    )
    secret_output = '{"text":"secret raw model content","extra":"untrusted field"}'

    with pytest.raises(ResponseValidationError) as captured:
        memory_response_validator(prepared, generation_request)(
            RawGenerationReceipt(text=secret_output, raw_candidate=secret_output),
            generation_request,
        )

    assert secret_output not in str(captured.value)
    assert "untrusted field" not in str(captured.value)


def test_memory_receipt_validator_enforces_policy_fact_limit_locally() -> None:
    from app.ai.generation_contracts import RawGenerationReceipt
    from app.ai.response_validation import ResponseValidationError
    from app.memory.producers import build_generation_request, memory_response_validator

    fact = {
        "content": "Mira hid the key.",
        "category": "information",
        "assertion_type": "occurrence",
        "entities": [],
        "attribution": [],
        "source_turns": ["t1"],
        "temporal_references": [],
        "importance": {"level": "major", "reason": "A key matters."},
    }
    prepared = request("facts")
    generation_request = build_generation_request(
        prepared,
        ModelConfig(
            provider="local",
            model="unit-model",
            max_tokens=731,
            destination_fingerprint="destination-hmac",
        ),
    )
    raw = json.dumps({"facts": [fact] * (prepared.facts_policy.max_per_batch + 1)})

    with pytest.raises(ResponseValidationError) as captured:
        memory_response_validator(prepared, generation_request)(
            RawGenerationReceipt(text=raw), generation_request
        )

    diagnostic = captured.value.diagnostics[0]
    assert diagnostic.path == ("facts",)
    assert diagnostic.code.value == "validation_failed"
    assert raw not in str(captured.value)
