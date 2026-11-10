from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.memory.batch_source_contracts import BatchInput
from app.memory.document_contracts import SummaryPayload
from app.memory.producer_contracts import (
    BatchPayload,
    FactsPayload,
    GeneratedEntity,
    GeneratedFact,
    validate_facts,
)
from app.memory.production_policy import FactsPolicy


def policy(*, cap: int = 5) -> FactsPolicy:
    return FactsPolicy.model_validate(
        {
            "max_per_batch": cap,
            "importance_levels": [
                {"name": "custom-high", "criteria": "Major change", "examples": "A secret"},
                {"name": "custom-low", "criteria": "Minor detail", "examples": "A meal"},
            ],
        }
    )


def source(*, extra_operations: tuple[dict[str, object], ...] = ()) -> BatchInput:
    turn_id = uuid4()
    operations = [
        {
            "id": uuid4(),
            "ordinal": index,
            "step": None,
            "beat": None,
            "payload": {
                "origin": "npc",
                "name": "create_npc",
                "outcome": "succeeded",
                "arguments": {"name": "Mira"},
                "result": {
                    "kind": "npc",
                    "npc_id": "npc-1",
                    "status": "created",
                    "action": None,
                    "axis_changes": {},
                },
                "deltas": (),
            },
        }
        for index in range(1, 2)
    ]
    operations.extend(extra_operations)
    return BatchInput.model_validate(
        {
            "turns": (
                {
                    "reference": "t1",
                    "turn_id": turn_id,
                    "player_action": "Ask Mira about the key",
                    "narration": "Mira admits she hid it.",
                    "operations": tuple(operations),
                },
                {
                    "reference": "t2",
                    "turn_id": uuid4(),
                    "player_action": "Wait",
                    "narration": "The party rests.",
                    "operations": None,
                },
            )
        }
    )


def fact_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "content": "Mira hid the key beneath the altar.",
        "category": "event",
        "assertion_type": "occurrence",
        "entities": [{"name": "Mira", "type": "npc", "role": "agent"}],
        "attribution": [],
        "source_turns": ["t1"],
        "temporal_references": [],
        "importance": {"level": "custom-high", "reason": "Reveals the central mystery."},
    }
    data.update(overrides)
    return data


def test_generated_fact_is_strict_immutable_and_does_not_accept_canonical_refs() -> None:
    fact = GeneratedFact.model_validate(fact_data())
    assert fact.source_turns == ("t1",)
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate({**fact_data(), "canonical_ref": {"type": "npc", "id": "1"}})
    with pytest.raises(ValidationError):
        GeneratedEntity.model_validate(
            {
                "name": "Mira",
                "type": "npc",
                "role": "agent",
                "canonical_ref": {"type": "npc", "id": "1"},
            }
        )
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate({**fact_data(), "id": "fact-1"})
    with pytest.raises(ValidationError):
        fact.content = "Changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content", " "),
        ("category", "opinion"),
        ("assertion_type", "guess"),
        ("entities", "Mira"),
        ("attribution", ["0"]),
        ("source_turns", [""]),
        ("source_turns", ["turn-1"]),
        ("temporal_references", ["  "]),
        ("importance", {"level": "", "reason": "Reason"}),
    ],
)
def test_generated_fact_requires_valid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate({**fact_data(), field: value})


def test_attribution_requires_unique_in_range_indices_and_non_occurrence_attribution() -> None:
    entity = [{"name": "Mira", "type": "npc", "role": "speaker"}]
    for indices in ([0, 0], [1], [-1], [True]):
        with pytest.raises(ValidationError):
            GeneratedFact.model_validate(fact_data(entities=entity, attribution=indices))
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate(fact_data(entities=entity, attribution=[0]))
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate(
            fact_data(assertion_type="belief", entities=entity, attribution=[])
        )
    assert GeneratedFact.model_validate(
        fact_data(assertion_type="statement", entities=entity, attribution=[0])
    )


def test_empty_fact_lists_are_valid_and_batch_cap_does_not_truncate() -> None:
    one = fact_data()
    assert FactsPayload.model_validate({"facts": []}).facts == ()
    with pytest.raises(ValidationError):
        FactsPayload.model_validate({"extra": True})
    with pytest.raises(ValidationError):
        FactsPayload.model_validate({"facts": [{**one, "content": 42}]})
    payload = FactsPayload.model_validate(
        {"facts": [one, {**one, "content": "A second distinct event."}]}
    )
    with pytest.raises(ValueError):
        validate_facts(payload, source(), policy(cap=1))


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_turns": ["t9"]},
        {"importance": {"level": "ordinary", "reason": "Reason"}},
    ],
)
def test_contextual_refs_and_importance_are_checked_during_resolution(
    overrides: dict[str, object],
) -> None:
    payload = FactsPayload.model_validate({"facts": [fact_data(**overrides)]})
    with pytest.raises(ValueError):
        validate_facts(payload, source(), policy())


def test_validation_resolves_batch_turns_and_only_unambiguous_created_npcs() -> None:
    payload = FactsPayload.model_validate({"facts": [fact_data()]})
    batch = source()
    resolved = validate_facts(payload, batch, policy())
    assert resolved[0].source_turn_ids == (batch.turns[0].turn_id,)
    assert resolved[0].metadata.entities[0].canonical_ref.type == "npc"
    assert resolved[0].metadata.entities[0].canonical_ref.id == "npc-1"


def test_duplicate_npc_name_is_left_unresolved_and_bad_source_refs_rejected() -> None:
    second = {
        "id": uuid4(),
        "ordinal": 2,
        "step": None,
        "beat": None,
        "payload": {
            "origin": "npc",
            "name": "create_npc",
            "outcome": "succeeded",
            "arguments": {"name": "Mira"},
            "result": {
                "kind": "npc",
                "npc_id": "npc-2",
                "status": "created",
                "action": None,
                "axis_changes": {},
            },
            "deltas": (),
        },
    }
    result = validate_facts(
        FactsPayload.model_validate({"facts": [fact_data()]}),
        source(extra_operations=(second,)),
        policy(),
    )
    assert result[0].metadata.entities[0].canonical_ref is None
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate(fact_data(source_turns=["t1", "t1"]))
    with pytest.raises(ValidationError):
        GeneratedFact.model_validate(fact_data(source_turns=[]))
    for refs in (["t3"],):
        payload = FactsPayload.model_validate({"facts": [fact_data(source_turns=refs)]})
        with pytest.raises(ValueError):
            validate_facts(payload, source(), policy())


def test_duplicate_source_turn_references_and_ids_are_rejected() -> None:
    batch = source()
    duplicate_ref = batch.model_copy(
        update={"turns": (batch.turns[0], batch.turns[0].model_copy(update={"turn_id": uuid4()}))}
    )
    duplicate_id = batch.model_copy(
        update={
            "turns": (
                batch.turns[0],
                batch.turns[1].model_copy(update={"turn_id": batch.turns[0].turn_id}),
            )
        }
    )
    payload = FactsPayload.model_validate({"facts": [fact_data()]})
    for invalid_source in (duplicate_ref, duplicate_id):
        with pytest.raises(ValueError):
            validate_facts(payload, invalid_source, policy())


def test_batch_payload_requires_summary_and_allows_empty_facts() -> None:
    entry = fact_data()
    assert BatchPayload.model_validate({"summary": {"text": "A summary"}, "facts": []}).facts == ()
    with pytest.raises(ValidationError):
        BatchPayload.model_validate({"facts": []})
    payload = BatchPayload.model_validate(
        {
            "summary": SummaryPayload(text="A summary"),
            "facts": [entry, {**entry, "content": "Another event."}],
        }
    )
    assert len(payload.facts) == 2


def test_identity_evidence_outside_the_cited_turns_is_not_used() -> None:
    payload = FactsPayload.model_validate({"facts": [fact_data(source_turns=["t2"])]})
    batch = source()
    result = validate_facts(payload, batch, policy())
    assert result[0].source_turn_ids == (batch.turns[1].turn_id,)
    assert result[0].metadata.entities[0].canonical_ref is None
