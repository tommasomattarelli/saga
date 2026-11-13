from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.response_contracts import ResponseContract, parse_json_document


class ExamplePayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    text: Annotated[str, Field(min_length=1)]
    count: Annotated[int, Field(ge=0, le=5)]


def contract(version: str = "example-v1") -> ResponseContract[ExamplePayload]:
    return ResponseContract(name="example", version=version, model_type=ExamplePayload)


def test_contract_validates_the_canonical_model() -> None:
    result = contract().validate('{"text":"A memory.","count":2}')

    assert isinstance(result, ExamplePayload)
    assert result.model_dump() == {"text": "A memory.", "count": 2}


@pytest.mark.parametrize(
    "raw",
    [
        '{"text":"","count":2}',
        '{"text":"A memory.","count":"2"}',
        '{"text":"A memory.","count":2.0}',
        '{"text":"A memory.","count":true}',
        '{"text":"A memory.","count":6}',
        '{"text":"A memory."}',
        '{"text":"A memory.","count":2,"invented":null}',
        '["A memory.",2]',
    ],
)
def test_contract_does_not_coerce_drop_or_invent_fields(raw: str) -> None:
    with pytest.raises(ValidationError):
        contract().validate(raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"text":"first","text":"second","count":2}',
        '{"nested":{"key":1,"key":2}}',
        '{"number":NaN}',
        '{"number":Infinity}',
        '{"number":-Infinity}',
        '{"number":1e9999}',
        '{"number":-1e9999}',
        '{"text":"A memory.","count":2',
        '{"text":"A memory.","count":2} {}',
        'prefix {"text":"A memory.","count":2}',
        '```json\n{"text":"A memory.","count":2}\n```',
    ],
)
def test_parser_rejects_ambiguous_invalid_or_wrapped_documents(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_json_document(raw)


def test_parser_preserves_valid_json_values_without_changing_content() -> None:
    raw = ' {"nested":[1,1.5,true,null,{"text":"brace { and fence ```"}]}\n'

    assert parse_json_document(raw) == {
        "nested": [1, 1.5, True, None, {"text": "brace { and fence ```"}]
    }


def test_schema_keeps_canonical_constraints_and_is_not_a_shared_mutable_dict() -> None:
    response_contract = contract()
    schema = response_contract.schema

    assert schema == ExamplePayload.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["text", "count"]
    schema.clear()
    assert response_contract.schema == ExamplePayload.model_json_schema()


def test_contract_schema_identity_is_stable_and_versioned() -> None:
    assert contract().schema_hash == contract().schema_hash
    assert contract().schema_hash != contract("example-v2").schema_hash
    assert (
        ResponseContract(name="other", version="example-v1", model_type=ExamplePayload).schema_hash
        != contract().schema_hash
    )


def test_contract_schema_identity_covers_the_actual_schema() -> None:
    class OtherPayload(ExamplePayload):
        count: Annotated[int, Field(ge=0, le=6)]

    other = ResponseContract(name="example", version="example-v1", model_type=OtherPayload)

    assert other.schema_hash != contract().schema_hash


def test_contract_identity_fields_are_frozen() -> None:
    response_contract = contract()

    with pytest.raises(FrozenInstanceError):
        response_contract.version = "example-v2"


@pytest.mark.parametrize("name,version", [("", "v1"), ("example", ""), (" ", "v1")])
def test_contract_requires_explicit_nonempty_name_and_version(name: str, version: str) -> None:
    with pytest.raises(ValueError):
        ResponseContract(name=name, version=version, model_type=ExamplePayload)
