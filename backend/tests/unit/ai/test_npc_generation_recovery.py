from __future__ import annotations

from typing import cast

import pytest

from app.ai.generation_contracts import FormatMode, GenerationRequest, RawGenerationReceipt
from app.ai.generation_errors import SchemaModeUnsupportedBeforeIO
from app.ai.generation_execution_ledger import (
    GenerationOutcomeStatus,
    InMemoryGenerationLedger,
)
from app.ai.npc_outcomes import NPCFailure, NPCSpeaking
from app.ai.router import ModelConfig
from app.core.psychology import DEFAULT_PSYCHOLOGY
from tests.unit.ai.npc_generation_test_support import (
    RecordingGenerationLedger,
    execution_identity,
    invoke_with,
    response,
)
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


async def test_invalid_receipt_is_recorded_then_corrected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = response(axis_changes={"trust": 1.5})
    provider = TypedResponseProvider([invalid, response(lines=["Corrected."])])
    ledgers: list[InMemoryGenerationLedger] = []
    monkeypatch.setattr(
        "app.ai.npc_director.InMemoryGenerationLedger",
        lambda: RecordingGenerationLedger(ledgers),
    )

    result = await invoke_with(monkeypatch, provider)

    assert result == NPCSpeaking("Lyra", ("Corrected.",))
    assert len(provider.requests) == 2
    assert provider.requests[0].logical_result_id == provider.requests[1].logical_result_id
    assert provider.requests[0].messages[0] == provider.requests[1].messages[0]
    history = await ledgers[0].history(execution_identity(provider.requests[0], 3), "actor")
    assert history[0].outcome is not None
    assert history[0].outcome.status is GenerationOutcomeStatus.INVALID
    assert history[0].outcome.receipt is not None
    assert history[0].outcome.receipt.text == invalid.text


@pytest.mark.parametrize(
    "raw",
    [
        '{"status":"speaking","lines":["Hello."],"axis_changes":[{"key":"trust","value":1},{"key":"trust","value":2}]}',
        '{"status":"speaking","lines":["Hello."],"axis_changes":[{"key":"trust","value":true}]}',
        '{"status":"speaking","lines":["Hello."],"axis_changes":[{"key":"unknown","value":1}]}',
        '{"status":"speaking","lines":["Hello.","Again.","Third.","Fourth.","Fifth."]}',
        '{"status":"speaking","lines":["[[npc:Lyra:1]]"]}',
    ],
)
async def test_invalid_receipts_recover_without_acceptance(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    provider = TypedResponseProvider([RawGenerationReceipt(text=raw), response(lines=["Valid."])])
    result = await invoke_with(monkeypatch, provider)
    assert isinstance(result, NPCSpeaking)
    assert result.lines == ("Valid.",)
    assert len(provider.requests) == 2


async def test_send_budget_is_per_actor_and_parallel_results_keep_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = {
        name: TypedResponseProvider(
            [response(axis_changes={"trust": 1.5}), response(lines=[f"{name} corrected."])]
        )
        for name in ("A", "B")
    }
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            side_effect=[
                (
                    provider,
                    ModelConfig(
                        "openai",
                        "test-model",
                        256,
                        destination_fingerprint="offline-test-destination",
                    ),
                )
                for provider in providers.values()
            ]
        ),
    )
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation_recovery_policy",
        lambda: __import__(
            "app.ai.generation_execution_ledger", fromlist=["GenerationRecoveryPolicy"]
        ).GenerationRecoveryPolicy(2),
    )
    import uuid

    from app.ai.npc_director import NPCInput, invoke_npcs_parallel

    results = await invoke_npcs_parallel(
        [NPCInput(name, {"name": name}, "Hello") for name in providers],
        uuid.uuid4(),
    )
    assert [result.lines for result in results if isinstance(result, NPCSpeaking)] == [
        ("A corrected.",),
        ("B corrected.",),
    ]
    assert [len(provider.requests) for provider in providers.values()] == [2, 2]


async def test_exhaustion_returns_failure_without_an_extra_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TypedResponseProvider([response(axis_changes={"trust": 1.5})])
    result = await invoke_with(monkeypatch, provider, budget=1)
    assert isinstance(result, NPCFailure)
    assert len(provider.requests) == 1


async def test_context_invalid_candidate_is_corrected_before_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = response(lines=["..."])
    provider = TypedResponseProvider([invalid, response(lines=["Corrected."])])
    from app.ai import npc_generation

    validate = npc_generation.validate_actor_response
    calls = 0

    def count(*args, **kwargs):
        nonlocal calls
        calls += 1
        return validate(*args, **kwargs)

    monkeypatch.setattr(npc_generation, "validate_actor_response", count)
    result = await invoke_with(monkeypatch, provider)
    assert result == NPCSpeaking("Lyra", ("Corrected.",))
    assert len(provider.requests) == 2
    assert calls == 2


@pytest.mark.parametrize(
    ("mode", "allow_json", "allow_prompt"),
    [
        (FormatMode.JSON_MODE, True, True),
        (FormatMode.PROMPT_ONLY, False, True),
    ],
)
async def test_executor_uses_only_explicitly_authorized_fallback_modes(
    monkeypatch: pytest.MonkeyPatch,
    mode: FormatMode,
    allow_json: bool,
    allow_prompt: bool,
) -> None:
    provider = TypedResponseProvider(
        [
            SchemaModeUnsupportedBeforeIO(),
            response(axis_changes={"trust": 2}, wire_entries=False),
        ]
    )
    result = await invoke_with(
        monkeypatch,
        provider,
        budget=2,
        allow_json_mode_fallback=allow_json,
        allow_prompt_only_fallback=allow_prompt,
    )
    assert len(provider.requests) == 2
    assert result == NPCSpeaking("Lyra", ("Hello.",), axis_changes={"trust": 2})
    assert [request.format_mode for request in provider.requests] == [
        FormatMode.STRICT_NATIVE,
        mode,
    ]
    assert provider.requests[0].canonical_schema == provider.requests[1].canonical_schema
    assert provider.requests[0].wire_schema == provider.requests[1].wire_schema
    assert provider.requests[1].identity.allow_json_mode_fallback is allow_json
    assert provider.requests[1].identity.allow_prompt_only_fallback is allow_prompt
    assert "JSON mode or prompt-only" in provider.requests[1].system_prompt
    assert provider.receipts == []


@pytest.mark.parametrize(
    ("mode", "allow_json"),
    [(FormatMode.JSON_MODE, True), (FormatMode.PROMPT_ONLY, False)],
)
async def test_fallback_then_context_correction_keeps_one_three_send_budget(
    monkeypatch: pytest.MonkeyPatch,
    mode: FormatMode,
    allow_json: bool,
) -> None:
    invalid = response(axis_changes={"unlisted_axis_canary": 1}, wire_entries=False)
    ledgers: list[InMemoryGenerationLedger] = []
    provider: TypedResponseProvider

    async def check_saved_failure(request: GenerationRequest) -> None:
        if len(provider.requests) == 3:
            history = await ledgers[0].history(
                execution_identity(provider.requests[0], 3), "actor"
            )
            assert history[1].outcome is not None
            assert history[1].outcome.status is GenerationOutcomeStatus.INVALID
            assert history[1].outcome.receipt is not None
            assert history[1].outcome.receipt.text == invalid.text

    provider = TypedResponseProvider(
        [
            SchemaModeUnsupportedBeforeIO(),
            invalid,
            response(lines=["Corrected."], axis_changes={"trust": 1}, wire_entries=False),
            response(lines=["Must not be sent."]),
        ],
        before_send=check_saved_failure,
    )
    monkeypatch.setattr(
        "app.ai.npc_director.InMemoryGenerationLedger",
        lambda: RecordingGenerationLedger(ledgers),
    )
    result = await invoke_with(
        monkeypatch,
        provider,
        budget=3,
        allow_json_mode_fallback=allow_json,
        allow_prompt_only_fallback=True,
    )
    assert result == NPCSpeaking("Lyra", ("Corrected.",), axis_changes={"trust": 1})
    assert [request.format_mode for request in provider.requests] == [
        FormatMode.STRICT_NATIVE,
        mode,
        mode,
    ]
    assert len(provider.requests) == 3
    assert len(provider.receipts) == 1
    history = await ledgers[0].history(execution_identity(provider.requests[0], 3), "actor")
    outcomes = [entry.outcome for entry in history]
    assert [entry.reservation.number for entry in history] == [1, 2, 3]
    assert [outcome.status for outcome in outcomes if outcome] == [
        GenerationOutcomeStatus.SCHEMA_MODE_UNSUPPORTED,
        GenerationOutcomeStatus.INVALID,
        GenerationOutcomeStatus.VALID,
    ]
    guidance = cast(str, provider.requests[2].messages[-1]["content"])
    assert "JSON object" in guidance
    assert "Object keys must be one of:" in guidance
    assert '"trust"' in guidance
    assert "unlisted_axis_canary" not in guidance
    assert provider.requests[2].identity.allow_json_mode_fallback is allow_json
    assert provider.requests[2].identity.allow_prompt_only_fallback is True


async def test_unpermitted_schema_fallback_does_not_send_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = TypedResponseProvider([SchemaModeUnsupportedBeforeIO(), response()])
    result = await invoke_with(monkeypatch, provider, budget=2)
    assert isinstance(result, NPCFailure)
    assert [request.format_mode for request in provider.requests] == [FormatMode.STRICT_NATIVE]
    assert len(provider.receipts) == 1


async def test_strict_unknown_axis_correction_lists_current_allowed_axes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    psychology = DEFAULT_PSYCHOLOGY.model_copy(deep=True)
    psychology.axes = {"loyalty": psychology.axes["trust"]}
    invalid = RawGenerationReceipt(
        text=(
            '{"status":"speaking","lines":["Hello."],"action":null,'
            '"axis_changes":[{"key":"private_axis_canary","value":4}],'
            '"reveals_secret":false}'
        )
    )
    provider = TypedResponseProvider(
        [invalid, response(lines=["Corrected."], axis_changes={"loyalty": 2})]
    )
    result = await invoke_with(monkeypatch, provider, psychology=psychology, budget=2)
    assert result == NPCSpeaking("Lyra", ("Corrected.",), axis_changes={"loyalty": 2})
    request = provider.requests[0]
    properties = cast(dict[str, object], request.wire_schema["properties"])
    axis_array = cast(dict[str, object], properties["axis_changes"])
    definitions = cast(dict[str, object], request.wire_schema["$defs"])
    entry = cast(dict[str, object], definitions["NPCAxisChangeEntry"])
    entry_properties = cast(dict[str, object], entry["properties"])
    key_schema = cast(dict[str, object], entry_properties["key"])
    assert axis_array["type"] == "array"
    assert key_schema["enum"] == ["loyalty"]
    assert request.identity.wire_schema_hash
    guidance = cast(str, provider.requests[1].messages[-1]["content"])
    assert '"loyalty"' in guidance
    assert "private_axis_canary" not in guidance
