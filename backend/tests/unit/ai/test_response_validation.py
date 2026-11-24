from typing import Annotated

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ai.response_contracts import ResponseContract
from app.ai.response_validation import (
    DiagnosticCode,
    Normalization,
    ResponseValidationError,
    validate_response,
    validation_diagnostics,
)


class Detail(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    count: Annotated[int, Field(ge=0)]


class Payload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    text: str
    details: list[Detail]


class NestedPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    summary: Detail
    records: dict[str, Detail]


def contract() -> ResponseContract[Payload]:
    return ResponseContract(name="payload", version="v1", model_type=Payload)


def test_valid_bare_and_complete_fenced_documents_return_provenance() -> None:
    raw = '{"text":"safe","details":[{"count":2}]}'

    bare = validate_response(f" \t{raw}\r\n", contract())
    fenced = validate_response(f"```json\r\n{raw}\r\n```", contract())
    fenced_lf = validate_response(f"```json\n{raw}\n```", contract())

    assert bare.model == Payload(text="safe", details=[Detail(count=2)])
    assert bare.normalization is Normalization.NONE
    assert fenced.model == bare.model
    assert fenced.normalization is Normalization.JSON_FENCE_V1
    assert fenced_lf.model == bare.model
    assert fenced_lf.normalization is Normalization.JSON_FENCE_V1


@pytest.mark.parametrize(
    "raw",
    [
        'prefix ```json\n{"text":"safe","details":[]}\n```',
        '```JSON\n{"text":"safe","details":[]}\n```',
        '```json\n{"text":"safe","details":[]}\n``` trailing',
        '```json\n{"text":"safe","details":[]}\n``` ```json\n{"text":"safe","details":[]}\n```',
        '```json\n{"text":"safe","details":[]}',
        '```json\n{"text":"safe","details":[]} {"text":"other","details":[]}\n```',
    ],
)
def test_ambiguous_or_partial_wrappers_are_not_salvaged(raw: str) -> None:
    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, contract())
    assert raised.value.__context__ is None


def test_schema_failure_is_not_retried_as_a_wrapper_parse_failure() -> None:
    with pytest.raises(ResponseValidationError) as raised:
        validate_response('{"text":"safe","details":[{"count":"2"}]}', contract())

    assert raised.value.normalization is Normalization.NONE
    assert raised.value.diagnostics[0].code == "expected_integer"
    assert raised.value.diagnostics[0].path == ("details", 0, "count")
    assert raised.value.__context__ is None


def test_pydantic_numeric_constraint_maps_to_stable_saga_diagnostic() -> None:
    with pytest.raises(ResponseValidationError) as raised:
        validate_response('{"text":"safe","details":[{"count":-1}]}', contract())

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code is DiagnosticCode.BELOW_MINIMUM
    assert diagnostic.path == ("details", 0, "count")


def test_untrusted_extra_field_name_is_not_exposed_in_diagnostics() -> None:
    secret_key = "credential-canary"
    raw = f'{{"text":"safe","details":[],"{secret_key}":"secret-value"}}'

    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, contract())

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "unexpected_field"
    assert diagnostic.path == ("<unknown>",)
    assert secret_key not in str(diagnostic)
    assert "secret-value" not in str(diagnostic)


def test_fenced_schema_failure_reports_provenance_and_safe_path() -> None:
    raw = '```json\n{"text":"safe","details":[{"count":"2"}]}\n```'

    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, contract())

    assert raised.value.normalization is Normalization.JSON_FENCE_V1
    assert raised.value.diagnostics[0].code == "expected_integer"
    assert raised.value.diagnostics[0].path == ("details", 0, "count")


def test_malformed_fenced_document_reports_fence_provenance() -> None:
    raw = '```json\n{"text":"safe","details":[]\n```'

    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, contract())

    assert raised.value.normalization is Normalization.JSON_FENCE_V1
    assert raised.value.diagnostics[0].code == "invalid_json"


def test_paths_follow_nested_models_but_redact_dynamic_map_keys() -> None:
    response_contract = ResponseContract(name="nested", version="v1", model_type=NestedPayload)
    raw = '{"summary":{"count":"bad"},"records":{"count":{"count":"bad"},"0":{"count":"bad"}}}'

    with pytest.raises(ResponseValidationError) as raised:
        validate_response(raw, response_contract)

    paths = [diagnostic.path for diagnostic in raised.value.diagnostics]
    assert paths == [
        ("summary", "count"),
        ("records", "<unknown>", "count"),
        ("records", "<unknown>", "count"),
    ]


def test_custom_validation_context_is_not_exposed() -> None:
    class ContextPayload(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        text: str

        @field_validator("text")
        @classmethod
        def reject_with_context_canary(cls, value: str) -> str:
            raise ValueError("validator context canary")

    response_contract = ResponseContract(name="context", version="v1", model_type=ContextPayload)

    with pytest.raises(ResponseValidationError) as raised:
        validate_response('{"text":"input canary"}', response_contract)

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "validation_failed"
    assert diagnostic.path == ("text",)
    assert "canary" not in str(diagnostic)


def test_custom_validator_type_error_propagates() -> None:
    class BrokenPayload(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        text: str

        @field_validator("text")
        @classmethod
        def fail_internally(cls, value: str) -> str:
            raise TypeError("internal canary")

    broken = ResponseContract(name="broken", version="v1", model_type=BrokenPayload)

    with pytest.raises(TypeError, match="internal canary"):
        validate_response('{"text":"safe"}', broken)


def test_validation_diagnostics_returns_allowlisted_codes_and_safe_schema_paths() -> None:
    try:
        NestedPayload.model_validate(
            {
                "summary": {"count": "bad"},
                "records": {"credential-canary": {"count": "bad"}},
                "extra-canary": "secret",
            },
            strict=True,
        )
    except ValidationError as error:
        diagnostics = validation_diagnostics(error, NestedPayload.model_json_schema())
    else:
        pytest.fail("invalid payload unexpectedly validated")

    assert [(item.code, item.path) for item in diagnostics] == [
        (DiagnosticCode.EXPECTED_INTEGER, ("summary", "count")),
        (DiagnosticCode.EXPECTED_INTEGER, ("records", "<unknown>", "count")),
        (DiagnosticCode.UNEXPECTED_FIELD, ("<unknown>",)),
    ]
    assert "credential-canary" not in str(diagnostics)
    assert "extra-canary" not in str(diagnostics)
    assert "secret" not in str(diagnostics)
