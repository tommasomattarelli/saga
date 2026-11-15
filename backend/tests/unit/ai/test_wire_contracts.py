from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai.tools.tools_npc import UpdateNpc
from app.ai.tools.tools_world import ChangeNpcPsychology
from app.ai.wire_contracts import decode_wire, encode_wire, wire_model_for

ToolModel = type[UpdateNpc] | type[ChangeNpcPsychology]


@pytest.mark.parametrize(
    ("model", "map_field", "payload"),
    [
        (
            UpdateNpc,
            "updates",
            {"name": "Mara", "updates": {"condition": "wounded", "faction": "Ash"}},
        ),
        (
            ChangeNpcPsychology,
            "changes",
            {"npc": "Mara", "changes": {"trust": -5, "fear": 8}},
        ),
    ],
)
def test_wire_round_trip_preserves_canonical_values(
    model: ToolModel, map_field: str, payload: dict[str, object]
) -> None:
    canonical = model.model_validate(payload, strict=True)
    wire = encode_wire(canonical)
    values = canonical.updates if isinstance(canonical, UpdateNpc) else canonical.changes

    assert wire.model_dump(mode="json")[map_field] == [
        {"key": key, "value": value} for key, value in values.items()
    ]
    assert decode_wire(model, wire.model_dump(mode="json")) == canonical


@pytest.mark.parametrize(
    ("model", "payload", "expected_map"),
    [
        (UpdateNpc, {"name": "Mara", "updates": {}}, "updates"),
        (ChangeNpcPsychology, {"npc": "Mara", "changes": {}}, "changes"),
        (UpdateNpc, {"name": "Mara", "updates": {}, "create": True}, "updates"),
        (ChangeNpcPsychology, {"npc": "Mara", "changes": {}, "reason": "betrayal"}, "changes"),
    ],
)
def test_wire_round_trip_preserves_empty_maps_and_nonmap_defaults(
    model: ToolModel, payload: dict[str, object], expected_map: str
) -> None:
    canonical = model.model_validate(payload, strict=True)

    assert decode_wire(model, encode_wire(canonical).model_dump(mode="json")) == canonical
    assert canonical.model_dump()[expected_map] == {}


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            UpdateNpc,
            {"name": "Mara", "updates": [{"key": "x", "value": "a"}, {"key": "x", "value": "b"}]},
        ),
        (
            ChangeNpcPsychology,
            {
                "npc": "Mara",
                "changes": [{"key": "trust", "value": 1}, {"key": "trust", "value": 2}],
            },
        ),
    ],
)
def test_decode_rejects_duplicate_map_keys(model: ToolModel, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="Duplicate"):
        decode_wire(model, payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (UpdateNpc, {"name": "Mara", "updates": [{"key": "x", "value": 1}]}),
        (ChangeNpcPsychology, {"npc": "Mara", "changes": [{"key": "trust", "value": True}]}),
        (UpdateNpc, {"name": "Mara", "updates": [], "unexpected": 1}),
        (UpdateNpc, {"name": "Mara"}),
        (ChangeNpcPsychology, {"npc": "Mara"}),
        (
            ChangeNpcPsychology,
            {"npc": "Mara", "changes": [{"key": "trust", "value": 1, "extra": 2}]},
        ),
    ],
)
def test_wire_validation_is_closed_and_strict(
    model: ToolModel, payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        decode_wire(model, payload)


@pytest.mark.parametrize(
    ("model", "map_field", "value_type", "description"),
    [
        (UpdateNpc, "updates", str, UpdateNpc.model_fields["updates"].description),
        (
            ChangeNpcPsychology,
            "changes",
            int,
            ChangeNpcPsychology.model_fields["changes"].description,
        ),
    ],
)
def test_wire_model_is_derived_and_preserves_field_metadata(
    model: ToolModel, map_field: str, value_type: type, description: str | None
) -> None:
    wire = wire_model_for(model)
    fields = wire.model_fields

    assert fields[map_field].description == description
    schema = wire.model_json_schema()
    entry_ref = schema["properties"][map_field]["items"]["$ref"].split("/")[-1]
    entry_schema = schema["$defs"][entry_ref]
    assert entry_schema["properties"]["value"]["type"] == (
        "integer" if value_type is int else "string"
    )
    for name, field in model.model_fields.items():
        if name != map_field:
            assert fields[name].description == field.description
            assert fields[name].default == field.default
            assert fields[name].is_required() == field.is_required()
