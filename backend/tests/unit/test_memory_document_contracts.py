import json

import pytest
from pydantic import ValidationError

from app.memory.document_contracts import (
    FactEntity,
    FactImportance,
    FactMetadata,
    GlobalPayload,
    SummaryPayload,
)


def test_summary_payload_round_trips_and_is_frozen() -> None:
    payload = SummaryPayload.model_validate({"text": "The gate was opened."})

    assert SummaryPayload.model_validate_json(payload.model_dump_json()) == payload
    with pytest.raises(ValidationError):
        payload.text = "Changed"


@pytest.mark.parametrize("text", ["", " \t\n "])
def test_summary_text_must_be_nonempty(text: str) -> None:
    with pytest.raises(ValidationError):
        SummaryPayload.model_validate({"text": text})


def test_global_payload_converts_lists_to_immutable_tuples() -> None:
    payload = GlobalPayload.model_validate(
        {
            "story_so_far": "The party reached the city.",
            "open_threads": ["Find the missing key"],
            "relationships": [],
            "resolved_threads": ["The bridge is repaired"],
        }
    )

    assert isinstance(payload.open_threads, tuple)
    assert payload.relationships == ()
    assert GlobalPayload.model_validate_json(payload.model_dump_json()) == payload
    with pytest.raises(TypeError):
        payload.open_threads[0] = "Changed"


def test_global_payload_requires_every_field_and_story_text() -> None:
    with pytest.raises(ValidationError):
        GlobalPayload.model_validate({"story_so_far": "Past"})
    with pytest.raises(ValidationError):
        GlobalPayload.model_validate(
            {
                "story_so_far": " ",
                "open_threads": [],
                "relationships": [],
                "resolved_threads": [],
            }
        )


def test_global_payload_rejects_empty_entries_and_unknown_fields() -> None:
    data = {
        "story_so_far": "Past",
        "open_threads": [""],
        "relationships": [],
        "resolved_threads": [],
    }
    with pytest.raises(ValidationError):
        GlobalPayload.model_validate(data)

    data["unexpected"] = "extra"
    with pytest.raises(ValidationError):
        GlobalPayload.model_validate(data)


def fact_data() -> dict[str, object]:
    return {
        "entities": [
            {
                "name": "Mira",
                "type": "player",
                "role": "speaker",
                "canonical_ref": {"type": "npc", "id": "npc-mira"},
            },
            {"name": "Crypt", "type": "location", "role": "subject"},
        ],
        "attribution": [0],
        "temporal_references": ["three days ago"],
        "importance": {"level": "critical", "reason": "A major secret was revealed."},
    }


def test_fact_metadata_round_trips_with_list_inputs_and_absent_canonical_ref() -> None:
    payload = FactMetadata.model_validate(fact_data())
    encoded = json.dumps(payload.model_dump(mode="json"))
    restored = FactMetadata.model_validate_json(encoded)

    assert payload == restored
    assert payload.entities[1].canonical_ref is None
    assert isinstance(payload.entities, tuple)
    assert isinstance(payload.temporal_references, tuple)


def test_explicit_null_is_allowed_only_for_optional_canonical_reference() -> None:
    entity = {"name": "Mira", "type": "npc", "role": "speaker", "canonical_ref": None}
    assert FactEntity.model_validate(entity).canonical_ref is None

    with pytest.raises(ValidationError):
        SummaryPayload.model_validate({"text": None})


def test_fact_metadata_allows_empty_collections() -> None:
    payload = FactMetadata.model_validate(
        {
            "entities": [],
            "attribution": [],
            "temporal_references": [],
            "importance": {"level": "custom", "reason": "Relevant source."},
        }
    )

    assert payload.entities == ()
    assert payload.attribution == ()
    assert payload.temporal_references == ()


@pytest.mark.parametrize("attribution", [[-1], [2], [0, 0], [True]])
def test_fact_metadata_rejects_invalid_attribution_indices(attribution: list[object]) -> None:
    data = fact_data()
    data["attribution"] = attribution

    with pytest.raises(ValidationError):
        FactMetadata.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "   "),
        ("type", "creature"),
        ("role", "\t"),
    ],
)
def test_fact_entity_requires_nonempty_known_values(field: str, value: str) -> None:
    entity = {"name": "Mira", "type": "npc", "role": "speaker"}
    entity[field] = value

    with pytest.raises(ValidationError):
        FactEntity.model_validate(entity)


@pytest.mark.parametrize(
    "reference", [None, {"type": "npc", "id": ""}, {"type": "dragon", "id": "x"}]
)
def test_canonical_reference_is_optional_but_validated_when_present(
    reference: dict[str, str] | None,
) -> None:
    entity = {"name": "Mira", "type": "npc", "role": "speaker"}
    if reference is not None:
        entity["canonical_ref"] = reference

    if reference is None:
        assert FactEntity.model_validate(entity).canonical_ref is None
        return
    with pytest.raises(ValidationError):
        FactEntity.model_validate(entity)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("level", ""),
        ("reason", "  "),
    ],
)
def test_fact_importance_requires_nonempty_text(field: str, value: str) -> None:
    data = {"level": "ordinary", "reason": "Evidence supports this."}
    data[field] = value

    with pytest.raises(ValidationError):
        FactImportance.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entities", "not a list"),
        ("attribution", ["0"]),
        ("temporal_references", [4]),
        ("importance", None),
        ("source_turns", ["not persisted here"]),
    ],
)
def test_fact_metadata_rejects_coercion_null_and_unknown_fields(field: str, value: object) -> None:
    data = fact_data()
    data[field] = value

    with pytest.raises(ValidationError):
        FactMetadata.model_validate(data)


def test_fact_entity_and_importance_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        FactEntity.model_validate(
            {"name": "Mira", "type": "npc", "role": "speaker", "extra": True}
        )
    with pytest.raises(ValidationError):
        FactImportance.model_validate({"level": "ordinary", "reason": "Why", "extra": True})
