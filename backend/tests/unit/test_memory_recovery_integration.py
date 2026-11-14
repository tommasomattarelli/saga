from __future__ import annotations

import json
from unittest.mock import Mock
from uuid import UUID

import pytest

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import Adapter
from app.ai.generation_execution_ledger import (
    GenerationAttempt,
    GenerationLedger,
    GenerationOutcomeStatus,
    GenerationRecoveryPolicy,
    GenerationSend,
    SendOutcome,
    SendReservation,
)
from app.ai.router import ModelConfig
from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import SummaryPayload
from app.memory.producer_prompts import PreparedMemoryRequest, ProducerKind, prepare_request
from app.memory.producers import (
    build_generation_request,
    execute_memory_generation,
)
from app.memory.production_policy import FactsPolicy


class MemoryTestLedger:
    def __init__(self) -> None:
        self.sends: list[GenerationSend] = []

    async def reserve(
        self, identity: str, role: str, max_sends: int, attempt: GenerationAttempt
    ) -> SendReservation:
        del identity, role
        if len(self.sends) >= max_sends:
            raise AssertionError("send limit exceeded")
        reservation = SendReservation(len(self.sends) + 1, attempt)
        self.sends.append(GenerationSend(reservation, None))
        return reservation

    async def record(self, identity: str, role: str, outcome: SendOutcome) -> None:
        del identity, role
        index = outcome.reservation.number - 1
        reserved = self.sends[index]
        assert reserved.reservation == outcome.reservation
        assert reserved.outcome is None
        self.sends[index] = GenerationSend(reserved.reservation, outcome)

    async def history(self, identity: str, role: str) -> tuple[GenerationSend, ...]:
        del identity, role
        return tuple(self.sends)


class MemoryTestProvider:
    def __init__(self, ledger: MemoryTestLedger, invalid: str, valid: str) -> None:
        self.ledger = ledger
        self.invalid = invalid
        self.valid = valid
        self.requests: list[GenerationRequest] = []

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.requests.append(request)
        if len(self.requests) == 1:
            return RawGenerationReceipt(text=self.invalid, raw_candidate=self.invalid)
        assert len(self.requests) == 2
        history = await self.ledger.history("", "")
        first = history[0].outcome
        assert first is not None
        assert first.status is GenerationOutcomeStatus.INVALID
        assert first.receipt is not None
        assert first.receipt.raw_candidate == self.invalid
        return RawGenerationReceipt(text=self.valid, raw_candidate=self.valid)


def prepared_request(kind: ProducerKind = "summary") -> PreparedMemoryRequest:
    batch = BatchInput.model_validate(
        {
            "turns": (
                {
                    "reference": "t1",
                    "turn_id": UUID("00000000-0000-0000-0000-000000000001"),
                    "player_action": "Ask Mira about the key",
                    "narration": "Mira hid the key.",
                    "operations": None,
                },
            )
        }
    )
    policy = FactsPolicy.model_validate(
        {
            "max_per_batch": 4,
            "importance_levels": [
                {"name": "major", "criteria": "Campaign-changing", "examples": "A betrayal"}
            ],
        }
    )
    return prepare_request(kind, batch, language="en", facts_policy=policy)


async def test_memory_consumer_recovers_invalid_output_and_reuses_valid_candidate() -> None:
    prepared = prepared_request()
    config = ModelConfig(
        provider="openai",
        model="offline-model",
        max_tokens=512,
        destination_fingerprint="offline-destination",
    )
    base = build_generation_request(prepared, config)
    ledger = MemoryTestLedger()
    ledger_protocol: GenerationLedger = ledger
    provider = MemoryTestProvider(
        ledger,
        '{"unexpected":"invalid candidate"}',
        '{"text":"Mira hid the key."}',
    )
    policy = GenerationRecoveryPolicy(max_sends_per_result=3)

    result = await execute_memory_generation(
        prepared,
        provider=provider,
        ledger=ledger_protocol,
        config=config,
        policy=policy,
        adapter=Adapter.OPENAI,
    )

    assert isinstance(result.payload, SummaryPayload)
    assert result.payload.text == "Mira hid the key."
    assert result.provider == config.provider
    assert result.model == config.model
    assert result.raw == '{"text":"Mira hid the key."}'
    assert len(provider.requests) == 2
    assert len(ledger.sends) == 2
    assert len(ledger.sends) <= policy.max_sends_per_result
    first, correction = provider.requests
    assert first.system_prompt == prepared.executor_system_prompt
    assert correction.system_prompt == prepared.executor_system_prompt
    assert correction.logical_result_id == base.logical_result_id
    assert correction.identity.logical_result_id == base.identity.logical_result_id
    assert correction.identity.role == base.identity.role
    assert correction.identity.contract_name == base.identity.contract_name
    assert correction.identity.contract_schema_hash == base.identity.contract_schema_hash
    assert correction.identity.destination_fingerprint == base.identity.destination_fingerprint
    assert correction.wire_schema == base.wire_schema
    assert correction.format_mode is base.format_mode
    assert correction.messages[: len(base.messages)] == base.messages
    correction_content = correction.messages[-2]["content"]
    assert isinstance(correction_content, str)
    assert "Untrusted model output JSON string" in correction_content
    assert ledger.sends[0].outcome is not None
    assert ledger.sends[0].outcome.receipt is not None
    assert ledger.sends[0].outcome.receipt.raw_candidate == provider.invalid
    assert first.identity.digest == base.identity.digest

    replay = await execute_memory_generation(
        prepared,
        provider=provider,
        ledger=ledger_protocol,
        config=config,
        policy=policy,
        adapter=Adapter.OPENAI,
    )

    assert replay.payload == result.payload
    assert len(provider.requests) == 2
    assert len(ledger.sends) == 2


def _fact(source_turn: str) -> dict[str, object]:
    return {
        "content": "Mira hid the key.",
        "category": "information",
        "assertion_type": "occurrence",
        "entities": [],
        "attribution": [],
        "source_turns": [source_turn],
        "temporal_references": [],
        "importance": {"level": "major", "reason": "A key matters."},
    }


def _facts_json(source_turn: str) -> str:
    return json.dumps({"facts": [_fact(source_turn)]})


async def test_valid_facts_generation_runs_contextual_validation_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory import producers

    prepared = prepared_request("facts")
    config = ModelConfig(
        provider="openai",
        model="offline-model",
        max_tokens=512,
        destination_fingerprint="offline-destination",
    )
    ledger = MemoryTestLedger()
    provider = MemoryTestProvider(ledger, _facts_json("t1"), _facts_json("t1"))
    policy = GenerationRecoveryPolicy(max_sends_per_result=3)
    validate_context = Mock(wraps=producers.validate_facts_context)
    monkeypatch.setattr(producers, "validate_facts_context", validate_context)

    result = await execute_memory_generation(
        prepared,
        provider=provider,
        ledger=ledger,
        config=config,
        policy=policy,
        adapter=Adapter.OPENAI,
    )

    validate_context.assert_called_once_with(
        result.payload, prepared.source, prepared.facts_policy
    )
    assert len(provider.requests) == 1
    assert len(ledger.sends) == 1
    assert len(result.facts) == 1


async def test_context_invalid_facts_are_corrected_before_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory import producers
    from app.memory.producer_contracts import FactsPayload

    prepared = prepared_request("facts")
    config = ModelConfig(
        provider="openai",
        model="offline-model",
        max_tokens=512,
        destination_fingerprint="offline-destination",
    )
    invalid = _facts_json("t999")
    valid = _facts_json("t1")
    ledger = MemoryTestLedger()
    provider = MemoryTestProvider(ledger, invalid, valid)
    policy = GenerationRecoveryPolicy(max_sends_per_result=3)
    base = build_generation_request(prepared, config)
    validate_context = Mock(wraps=producers.validate_facts_context)
    monkeypatch.setattr(producers, "validate_facts_context", validate_context)

    result = await execute_memory_generation(
        prepared,
        provider=provider,
        ledger=ledger,
        config=config,
        policy=policy,
        adapter=Adapter.OPENAI,
    )

    assert isinstance(result.payload, FactsPayload)
    assert len(result.facts) == 1
    assert result.raw == valid
    assert validate_context.call_count == 2
    assert len(provider.requests) == 2
    assert len(ledger.sends) == 2
    assert ledger.sends[0].outcome is not None
    assert ledger.sends[0].outcome.status is GenerationOutcomeStatus.INVALID
    assert ledger.sends[0].outcome.receipt is not None
    assert ledger.sends[0].outcome.receipt.raw_candidate == invalid
    first, correction = provider.requests
    assert correction.logical_result_id == base.logical_result_id
    assert correction.wire_schema == base.wire_schema
    assert correction.format_mode is base.format_mode
    correction_content = correction.messages[-2]["content"]
    assert isinstance(correction_content, str)
    assert "Untrusted model output JSON string" in correction_content
