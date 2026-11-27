import json
import re
from typing import Literal

import pytest

from app.ai.prompts.loader import template
from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import GlobalPayload, SummaryPayload
from app.memory.producer_contracts import BatchPayload, FactsPayload
from app.memory.producer_examples import worked_example
from app.memory.producer_prompts import PreparedMemoryRequest, ProducerKind, prepare_request
from app.memory.production_policy import FactsPolicy


def policy(cap: int = 3) -> FactsPolicy:
    return FactsPolicy.model_validate(
        {
            "max_per_batch": cap,
            "importance_levels": [
                {"name": "custom", "criteria": "Substantial evidence", "examples": "A promise"},
                {"name": "lesser", "criteria": "Meaningful but smaller", "examples": "A clue"},
            ],
        }
    )


def parse_example(
    kind: Literal["batch", "summary", "facts", "global"], cap: int = 3
) -> dict[str, object]:
    rendered = worked_example(kind, policy(cap))
    match = re.fullmatch(r"<worked_example>(\{.*\})</worked_example>", rendered, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))


@pytest.mark.parametrize("kind", ["batch", "summary", "facts", "global"])
def test_rendered_examples_are_one_delimited_json_object_and_match_output_schema(
    kind: str,
) -> None:
    data = parse_example(kind)
    expected = {
        "batch": BatchPayload,
        "summary": SummaryPayload,
        "facts": FactsPayload,
        "global": GlobalPayload,
    }[kind]
    expected.model_validate_json(json.dumps(data["output"]))
    assert set(data) == (
        {"source", "output", "previous"} if kind == "global" else {"source", "output"}
    )
    source = BatchInput.model_validate_json(json.dumps(data["source"]))
    assert len(source.turns) == 2
    assert all(turn.operations is None for turn in source.turns)


def test_fact_example_teaches_all_four_fact_types_with_attribution() -> None:
    output = FactsPayload.model_validate_json(json.dumps(parse_example("facts", 4)["output"]))
    assert [fact.assertion_type for fact in output.facts] == [
        "statement",
        "intention",
        "belief",
        "occurrence",
    ]
    assert output.facts[0].category == "information"
    assert output.facts[0].entities[0].name == "the player"
    assert output.facts[1].category == "commitment"
    assert output.facts[1].attribution == (1,)
    assert output.facts[1].entities[1].name == "Neris"
    assert output.facts[2].assertion_type == "belief"
    assert output.facts[2].attribution == (0,)
    assert output.facts[2].entities[0].name == "Mira"
    assert output.facts[3].assertion_type == "occurrence"
    assert output.facts[3].attribution == ()
    assert len(output.facts[3].source_turns) == 1
    assert output.facts[3].source_turns[0] == "t2"
    assert all(
        entity.model_dump().get("canonical_ref") is None
        for fact in output.facts
        for entity in fact.entities
    )


def test_fact_example_teaches_attribution_indices_are_local_to_each_fact() -> None:
    output = FactsPayload.model_validate_json(json.dumps(parse_example("facts", 4)["output"]))
    player_report, commitment = output.facts[0], output.facts[1]
    assert [entity.name for entity in player_report.entities] == [
        "the player",
        "Morrowglass",
        "Neris",
    ]
    assert [entity.name for entity in commitment.entities] == ["the player", "Neris"]
    assert commitment.attribution == (1,)
    assert commitment.entities[commitment.attribution[0]].name == "Neris"


def test_fact_example_separates_player_report_from_npc_commitment() -> None:
    output = FactsPayload.model_validate_json(json.dumps(parse_example("facts")["output"]))
    report = next(fact for fact in output.facts if fact.assertion_type == "statement")
    commitment = next(fact for fact in output.facts if fact.assertion_type == "intention")

    assert output.facts[0] == report
    assert output.facts[1] == commitment
    assert report.category == "information"
    assert "Morrowglass" in report.content
    speaker = report.entities[report.attribution[0]]
    assert (speaker.name, speaker.type) == ("the player", "player")
    source_indices = {
        index for index, entity in enumerate(report.entities) if entity.name == "Morrowglass"
    }
    assert source_indices.isdisjoint(report.attribution)
    assert "charter" not in commitment.content


@pytest.mark.parametrize(("cap", "expected"), [(0, 0), (1, 1), (3, 3), (4, 4)])
def test_fact_example_obeys_configured_cap_and_importance_level(cap: int, expected: int) -> None:
    payload = FactsPayload.model_validate_json(json.dumps(parse_example("facts", cap)["output"]))
    assert len(payload.facts) == expected
    assert all(fact.importance.level == "custom" for fact in payload.facts)
    if cap == 3:
        assert all(fact.assertion_type != "occurrence" for fact in payload.facts)


def test_batch_example_combines_summary_and_facts_under_one_output_and_turn_membership() -> None:
    data = parse_example("batch")
    output = BatchPayload.model_validate_json(json.dumps(data["output"]))
    source = BatchInput.model_validate_json(json.dumps(data["source"]))
    assert isinstance(output.summary, SummaryPayload)
    assert {ref for fact in output.facts for ref in fact.source_turns} <= {
        turn.reference for turn in source.turns
    }
    assert "Mira explicitly says" not in output.summary.text


def test_global_example_is_a_full_checkpoint_with_prior_unresolved_thread_preserved() -> None:
    data = parse_example("global")
    previous = GlobalPayload.model_validate_json(json.dumps(data["previous"]))
    output = GlobalPayload.model_validate_json(json.dumps(data["output"]))
    assert any("smugglers" in thread for thread in previous.open_threads)
    assert any("smugglers" in thread for thread in output.open_threads)
    assert any("bronze key" in thread for thread in output.resolved_threads)
    assert any("flood" in thread for thread in output.resolved_threads)
    assert "holds the bronze key" not in output.story_so_far.lower()


def test_templates_keep_instructions_and_add_source_and_kind_specific_output_examples() -> None:
    assert "Distinguish intentions, failed attempts" in template("memory_summary", "instructions")
    assert "promise is not its fulfilment" in template("memory_facts", "instructions")
    assert "complete consolidated historical checkpoint" in template(
        "memory_global", "instructions"
    )
    assert BatchInput.model_validate_json(template("memory_production", "example_source"))
    assert SummaryPayload.model_validate_json(template("memory_summary", "example_output"))
    assert FactsPayload.model_validate_json(template("memory_facts", "example_output"))
    assert GlobalPayload.model_validate_json(template("memory_global", "example_output"))
    assert GlobalPayload.model_validate_json(template("memory_global", "previous"))


def test_example_marks_itself_as_illustrative_not_batch_evidence_or_rubric_rank() -> None:
    for name in ("memory_production", "memory_facts"):
        text = template(name, "example")
        assert "illustrat" in text.lower()
    assert "current batch" in template("memory_production", "example").lower()
    assert "actual criteria" in template("memory_facts", "example").lower()


def test_real_prompt_includes_one_isolated_example_and_composes_specialist_outputs() -> None:
    source = BatchInput.model_validate_json(template("memory_production", "example_source"))
    request = prepare_request("batch", source, language="it", facts_policy=policy())
    assert request.system_prompt.count("<worked_example>") == 1
    assert "not evidence for the current batch" in request.system_prompt
    assert "actual criteria" in request.system_prompt
    assert parse_example("batch")["output"] == {
        "summary": parse_example("summary")["output"],
        "facts": parse_example("facts")["output"]["facts"],
        "relations": parse_example("facts")["output"]["relations"],
    }
    assert parse_example("facts")["output"]["relations"]


@pytest.mark.parametrize("kind", ["batch", "summary"])
def test_summary_instructions_define_dm_memory_without_losing_continuity(
    kind: ProducerKind,
) -> None:
    source = BatchInput.model_validate_json(template("memory_production", "example_source"))
    prepared = prepare_request(kind, source, language="it", facts_policy=policy())
    instructions = template("memory_summary", "instructions")
    assert instructions in prepared.system_prompt
    for requirement in (
        "memory for the Dungeon Master",
        "third person",
        "causal sequence",
        "unresolved clues",
        "injuries",
        "time and travel constraints",
        "only once unless later evidence changes",
        "not a retelling",
        "Do not add literary embellishment",
        "source-format metadata",
    ):
        assert requirement in instructions


@pytest.mark.parametrize(
    ("template_name", "affected"),
    [("memory_summary", {"batch", "summary"}), ("memory_facts", {"batch", "facts"})],
)
def test_specialist_instruction_changes_affect_only_requests_using_that_specialist(
    monkeypatch: pytest.MonkeyPatch,
    template_name: str,
    affected: set[ProducerKind],
) -> None:
    from app.memory import producer_prompts
    from app.memory.production_policy import GlobalPolicy

    source = BatchInput.model_validate_json(template("memory_production", "example_source"))

    def prepare(kind: ProducerKind) -> PreparedMemoryRequest:
        return prepare_request(
            kind,
            source,
            language="it",
            facts_policy=policy(),
            global_policy=GlobalPolicy(target_words=100) if kind == "global" else None,
        )

    kinds: tuple[ProducerKind, ...] = ("batch", "summary", "facts", "global")
    baseline = {kind: prepare(kind) for kind in kinds}
    monkeypatch.setattr(
        producer_prompts,
        "template",
        lambda name, key: (
            "Alternative specialist instruction."
            if (name, key) == (template_name, "instructions")
            else template(name, key)
        ),
    )
    for kind in kinds:
        changed = prepare(kind)
        assert changed.source_hash == baseline[kind].source_hash
        assert changed.user_prompt == baseline[kind].user_prompt
        if kind in affected:
            assert changed.instruction_hash != baseline[kind].instruction_hash
        else:
            assert changed == baseline[kind]


@pytest.mark.parametrize("kind", ["batch", "facts"])
def test_fact_instructions_prioritize_future_recall_over_action_logs(kind: ProducerKind) -> None:
    source = BatchInput.model_validate_json(template("memory_production", "example_source"))
    prepared = prepare_request(kind, source, language="it", facts_policy=policy())
    instructions = template("memory_facts", "instructions")
    assert instructions in prepared.system_prompt
    for requirement in (
        "useful for future recall",
        "not a turn-by-turn action log",
        "lasting consequences",
        "small supported details",
        "outcomes over individual combat moves",
        "maximum, not a target",
        "independently understandable",
        "Do not bundle unrelated claims",
        "Do not invent future significance",
    ):
        assert requirement in instructions
