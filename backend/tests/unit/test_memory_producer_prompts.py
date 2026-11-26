from app.ai.prompts.loader import template
from app.config_loader import load_saga_config
from app.memory.producer_examples import worked_example
from app.memory.producer_prompts import (
    PRODUCER_VERSION,
    canonical,
    digest,
    prepare_request,
)
from app.memory.production_policy import FactsPolicy, GlobalPolicy
from tests.unit.test_memory_producers import facts_policy, request, schema_object, source


def test_batch_and_split_prompts_share_specialist_instructions_and_one_output_contract() -> None:
    combined = request("batch")
    summary = request("summary")
    facts = request("facts")
    summary_instructions = template("memory_summary", "instructions")
    facts_instructions = template("memory_facts", "instructions")
    assert summary_instructions in combined.system_prompt
    assert facts_instructions in combined.system_prompt
    assert summary_instructions in summary.system_prompt
    assert facts_instructions not in summary.system_prompt
    assert facts_instructions in facts.system_prompt
    assert summary_instructions not in facts.system_prompt
    assert combined.system_prompt.count("JSON") + combined.user_prompt.count("JSON") >= 1


def test_legacy_prompt_keeps_head_schema_manifest_while_executor_prompt_is_schema_free() -> None:
    prepared = request("facts")
    settings = {
        "language": "it",
        "facts_policy": prepared.facts_policy.model_dump(mode="json"),
        "global_policy": None,
    }
    legacy_sections = [
        template("memory_production", "system"),
        template("memory_facts", "instructions"),
        template("memory_production", "example"),
        template("memory_facts", "example"),
        worked_example("facts", prepared.facts_policy),
        canonical(settings),
        template("memory_production", "output"),
        canonical(prepared.response_schema),
    ]
    executor_sections = [
        *legacy_sections[:-2],
        template("memory_production", "executor_output"),
    ]

    assert PRODUCER_VERSION == "memory-v1"
    assert prepared.system_prompt == "\n\n".join(legacy_sections)
    assert "matching the following schema" in prepared.system_prompt
    assert canonical(prepared.response_schema) in prepared.system_prompt
    assert prepared.executor_system_prompt == "\n\n".join(executor_sections)
    assert "structured response contract" in prepared.executor_system_prompt
    assert canonical(prepared.response_schema) not in prepared.executor_system_prompt
    assert prepared.instruction_hash == digest("memory-v1\n" + prepared.system_prompt)


def test_fact_instructions_scope_speaker_boundaries_to_batch_and_facts_prompts() -> None:
    rules = (
        "Speaker boundaries: `player_action` is the player's own words and claims",
        "A declarative fact (statement, belief, intention) reports exactly one",
        "preface, context or summary",
        "the attribution is the reporter",
        "Indices are local to",
        "Do not merge an occurrence with a statement",
    )
    for kind in ("batch", "facts"):
        prepared = request(kind)
        assert all(rule in prepared.system_prompt for rule in rules)
    for kind in ("summary", "global"):
        prepared = request(
            kind, global_policy=GlobalPolicy(target_words=200) if kind == "global" else None
        )
        assert not any(rule in prepared.system_prompt for rule in rules)


def test_prompt_keeps_all_turn_source_verbatim_including_empty_operations() -> None:
    batch = source(
        action="CHASE the silver fox", narration="It vanishes into fog.", operations=False
    )
    prepared = request("batch", batch)
    for text in ("CHASE the silver fox", "It vanishes into fog.", '"operations":null'):
        assert text in prepared.user_prompt
    assert request("batch").user_prompt.count("create_npc") == 1


def test_campaign_language_and_full_importance_rubric_are_in_prompt() -> None:
    prepared = request("facts")
    for text in ("it", "Changes the campaign", "A betrayal", "Adds color", "A shared meal"):
        assert text in prepared.user_prompt or text in prepared.system_prompt
    assert "4" in prepared.user_prompt or "4" in prepared.system_prompt


def test_prepared_request_exposes_policy_enriched_schema_without_prompt_duplication() -> None:
    prepared = request("facts")
    schema = schema_object(prepared.response_schema)
    properties = schema_object(schema["properties"])
    definitions = schema_object(schema["$defs"])
    facts_schema = schema_object(properties["facts"])
    importance = schema_object(definitions["FactImportance"])
    importance_properties = schema_object(importance["properties"])
    level_schema = schema_object(importance_properties["level"])

    assert facts_schema["maxItems"] == 4
    assert level_schema["enum"] == ["major", "minor"]
    from app.memory.producer_prompts import canonical

    assert canonical(schema) not in prepared.executor_system_prompt
    assert "A betrayal" in prepared.executor_system_prompt


def test_all_native_prompts_use_real_contract_schemas_and_keep_worked_json_examples() -> None:
    from app.memory.producer_examples import worked_example
    from app.memory.producer_prompts import OUTPUT_MODELS, canonical

    for kind, model in OUTPUT_MODELS.items():
        prepared = (
            request(kind, global_policy=GlobalPolicy(target_words=200))
            if kind == "global"
            else request(kind)
        )
        assert prepared.response_schema == model.model_json_schema() or (
            kind in {"batch", "facts"}
            and schema_object(schema_object(prepared.response_schema["properties"])["facts"])[
                "maxItems"
            ]
            == prepared.facts_policy.max_per_batch
        )
        assert canonical(prepared.response_schema) not in prepared.executor_system_prompt
        assert worked_example(kind, prepared.facts_policy) in prepared.executor_system_prompt


def test_request_schema_is_independent_and_enriched_for_each_policy() -> None:
    first = prepare_request("facts", source(), language="it", facts_policy=facts_policy(cap=2))
    second = prepare_request("facts", source(), language="it", facts_policy=facts_policy(cap=7))

    first_schema = schema_object(first.response_schema)
    first_properties = schema_object(first_schema["properties"])
    first_facts = schema_object(first_properties["facts"])
    first_definitions = schema_object(first_schema["$defs"])
    importance = schema_object(first_definitions["FactImportance"])
    importance_properties = schema_object(importance["properties"])
    level_schema = schema_object(importance_properties["level"])
    second_schema = schema_object(second.response_schema)
    second_properties = schema_object(second_schema["properties"])
    second_facts = schema_object(second_properties["facts"])

    assert first_facts["maxItems"] == 2
    assert second_facts["maxItems"] == 7
    assert level_schema["enum"] == ["major", "minor"]


def test_configured_facts_policy_renders_explicit_max_and_yaml_rubric() -> None:

    configured = load_saga_config()["memory"]["production"]["facts"]
    policy = FactsPolicy.model_validate(
        {"max_per_batch": 7, "importance_levels": configured["importance_levels"]}
    )
    prepared = prepare_request("facts", source(), language="it", facts_policy=policy)
    for text in (
        '"max_per_batch":7',
        "A significant historical detail worth recalling",
        "A useful attributed clue",
        "substantially changes the campaign's stakes",
        "A central betrayal",
    ):
        assert text in prepared.system_prompt or text in prepared.user_prompt


def test_configured_importance_includes_central_revelations_before_action() -> None:
    from app.memory.production_policy import configured_memory_policy

    configured = configured_memory_policy().facts
    critical = next(level for level in configured.importance_levels if level.name == "critical")
    assert "central to an unresolved campaign mystery" in critical.criteria
    assert "before a resulting decision or action" in critical.criteria
    assert "a revelation redefining a central mystery" in critical.examples
    for kind in ("batch", "facts"):
        prepared = prepare_request(kind, source(), language="it", facts_policy=configured)
        assert critical.criteria in prepared.system_prompt
        assert critical.examples in prepared.system_prompt
