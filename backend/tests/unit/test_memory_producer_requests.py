import pytest

from app.ai.router import ModelConfig
from app.memory.producer_prompts import prepare_request
from tests.unit.test_memory_producers import facts_policy, request, schema_object, source


def test_request_hashes_track_source_and_instruction_independently() -> None:
    batch = source()
    first = request("facts", batch)
    assert first.source_hash == batch.source_hash()
    changed_source = prepare_request(
        "facts", source(action="Open the door"), language="it", facts_policy=facts_policy()
    )
    assert first.source_hash != changed_source.source_hash
    assert first.instruction_hash == changed_source.instruction_hash
    changed_language = prepare_request("facts", batch, language="en", facts_policy=facts_policy())
    assert first.source_hash == changed_language.source_hash
    assert first.instruction_hash != changed_language.instruction_hash


def test_generation_request_factory_freezes_each_memory_role_and_effective_policy() -> None:
    from uuid import UUID

    from app.ai.generation_contracts import FormatMode
    from app.ai.session_affinity import campaign_session
    from app.memory.producers import build_generation_request

    config = ModelConfig(
        provider="openrouter",
        model="unit-model",
        max_tokens=731,
        destination_fingerprint="destination-hmac",
        allow_json_mode_fallback=True,
        allow_prompt_only_fallback=False,
    )
    with campaign_session(UUID("00000000-0000-0000-0000-000000000001")):
        summary_prepared = request("summary")
        facts_prepared = request("facts")
        summary = build_generation_request(summary_prepared, config)
        facts = build_generation_request(facts_prepared, config)

    assert summary.contract.name == "memory-summary"
    assert summary.role == "summary"
    assert summary.format_mode is FormatMode.STRICT_NATIVE
    assert summary.output_limit.effective == 731
    assert summary.allow_json_mode_fallback is True
    assert summary.allow_prompt_only_fallback is False
    assert summary.session_affinity == "00000000-0000-0000-0000-000000000001"
    assert summary.system_prompt == summary_prepared.executor_system_prompt
    assert summary.canonical_schema == summary_prepared.response_schema
    assert summary.wire_schema == summary.canonical_schema
    facts_properties = schema_object(facts.canonical_schema["properties"])
    facts_schema = schema_object(facts_properties["facts"])
    assert facts_schema["maxItems"] == 4
    assert facts.wire_schema == facts.canonical_schema
    assert summary.logical_result_id != facts.logical_result_id


def test_generation_request_identity_changes_with_source_policy_model_and_role() -> None:
    from dataclasses import replace

    from app.memory.producers import build_generation_request

    config = ModelConfig(
        provider="local",
        model="unit-model",
        max_tokens=731,
        destination_fingerprint="destination-hmac",
    )
    baseline = build_generation_request(request("facts"), config)
    changed_source = build_generation_request(
        request("facts", source(action="Open the door")), config
    )
    changed_policy = build_generation_request(
        prepare_request("facts", source(), language="it", facts_policy=facts_policy(cap=7)),
        config,
    )
    changed_model = build_generation_request(
        request("facts"), replace(config, model="other-model")
    )
    changed_provider = build_generation_request(
        request("facts"), replace(config, provider="openai")
    )
    changed_destination = build_generation_request(
        request("facts"), replace(config, destination_fingerprint="other-destination")
    )
    changed_output_limit = build_generation_request(
        request("facts"), replace(config, max_tokens=732)
    )
    changed_fallback = build_generation_request(
        request("facts"), replace(config, allow_json_mode_fallback=True)
    )

    assert (
        len(
            {
                baseline.logical_result_id,
                changed_source.logical_result_id,
                changed_policy.logical_result_id,
                changed_model.logical_result_id,
                changed_provider.logical_result_id,
                changed_destination.logical_result_id,
                changed_output_limit.logical_result_id,
                changed_fallback.logical_result_id,
            }
        )
        == 8
    )


def test_generation_request_requires_a_resolved_destination_identity() -> None:
    from app.memory.producers import build_generation_request

    with pytest.raises(ValueError, match="destination fingerprint"):
        build_generation_request(
            request("summary"),
            ModelConfig(provider="local", model="unit-model", max_tokens=731),
        )
