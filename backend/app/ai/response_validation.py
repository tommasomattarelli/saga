from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ValidationError

from app.ai.response_contracts import ResponseContract

_JSON_FENCE = re.compile(
    r"\A[ \t\r\n]*```json(?:\r\n|\n)(.*?)(?:\r\n|\n)```[ \t\r\n]*\Z", re.DOTALL
)


class DiagnosticCode(StrEnum):
    INVALID_JSON = "invalid_json"
    TOOL_NOT_REGISTERED = "tool_not_registered"
    TOOL_UNAVAILABLE = "tool_unavailable"
    MISSING = "missing"
    UNEXPECTED_FIELD = "unexpected_field"
    EXPECTED_BOOLEAN = "expected_boolean"
    EXPECTED_INTEGER = "expected_integer"
    EXPECTED_NUMBER = "expected_number"
    EXPECTED_STRING = "expected_string"
    EXPECTED_ARRAY = "expected_array"
    EXPECTED_OBJECT = "expected_object"
    INVALID_ENUM = "invalid_enum"
    BELOW_MINIMUM = "below_minimum"
    ABOVE_MAXIMUM = "above_maximum"
    BELOW_MINIMUM_LENGTH = "below_minimum_length"
    ABOVE_MAXIMUM_LENGTH = "above_maximum_length"
    VALIDATION_FAILED = "validation_failed"


class Normalization(StrEnum):
    NONE = "none"
    JSON_FENCE_V1 = "json_fence_v1"


@dataclass(frozen=True)
class ValidationDiagnostic:
    code: DiagnosticCode
    path: tuple[str | int, ...]


class ResponseValidationError(Exception):
    def __init__(
        self,
        diagnostics: tuple[ValidationDiagnostic, ...],
        normalization: Normalization = Normalization.NONE,
    ) -> None:
        super().__init__("Response validation failed.")
        self.diagnostics = diagnostics
        self.normalization = normalization


@dataclass(frozen=True)
class ValidatedResponse[T: BaseModel]:
    model: T
    normalization: Normalization


def resolve_schema(schema: object, root: Mapping[str, object]) -> dict[str, object]:
    while isinstance(schema, dict):
        reference = schema.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
            return schema
        definition = reference.removeprefix("#/$defs/").replace("~1", "/").replace("~0", "~")
        definitions = root.get("$defs")
        if not isinstance(definitions, dict) or not isinstance(definitions.get(definition), dict):
            return {}
        schema = definitions[definition]
    return {}


def _child_schema(
    schema: Mapping[str, object], root: Mapping[str, object], segment: object
) -> tuple[str | int, dict[str, object]]:
    schema = resolve_schema(schema, root)
    properties = schema.get("properties")
    additional_properties = schema.get("additionalProperties")
    if isinstance(segment, str) and isinstance(properties, dict) and segment in properties:
        child = properties[segment]
        return segment, child if isinstance(child, dict) else {}
    if isinstance(additional_properties, dict):
        return "<unknown>", additional_properties
    if isinstance(segment, int) and "items" in schema:
        child = schema["items"]
        return segment, child if isinstance(child, dict) else {}
    return "<unknown>", {}


def _safe_path(
    location: Sequence[object], root_schema: Mapping[str, object]
) -> tuple[str | int, ...]:
    path: list[str | int] = []
    schema: Mapping[str, object] = root_schema
    for segment in location:
        safe_segment, schema = _child_schema(schema, root_schema, segment)
        path.append(safe_segment)
    return tuple(path)


def safe_path(
    location: Sequence[object], root_schema: Mapping[str, object]
) -> tuple[str | int, ...]:
    return _safe_path(location, root_schema)


def schema_at_path(
    root_schema: Mapping[str, object], path: Sequence[str | int]
) -> dict[str, object]:
    schema: Mapping[str, object] = root_schema
    for segment in path:
        schema = resolve_schema(schema, root_schema)
        if segment == "<unknown>":
            additional_properties = schema.get("additionalProperties")
            if isinstance(additional_properties, dict):
                schema = additional_properties
                continue
            return {}
        if isinstance(segment, int):
            items = schema.get("items")
            schema = items if isinstance(items, dict) else {}
            continue
        properties = schema.get("properties")
        child = properties.get(segment) if isinstance(properties, dict) else None
        schema = child if isinstance(child, dict) else {}
    return resolve_schema(schema, root_schema)


_PYDANTIC_CODES = {
    "bool_type": DiagnosticCode.EXPECTED_BOOLEAN,
    "bool_parsing": DiagnosticCode.EXPECTED_BOOLEAN,
    "int_type": DiagnosticCode.EXPECTED_INTEGER,
    "int_parsing": DiagnosticCode.EXPECTED_INTEGER,
    "float_type": DiagnosticCode.EXPECTED_NUMBER,
    "float_parsing": DiagnosticCode.EXPECTED_NUMBER,
    "string_type": DiagnosticCode.EXPECTED_STRING,
    "string_parsing": DiagnosticCode.EXPECTED_STRING,
    "list_type": DiagnosticCode.EXPECTED_ARRAY,
    "tuple_type": DiagnosticCode.EXPECTED_ARRAY,
    "set_type": DiagnosticCode.EXPECTED_ARRAY,
    "frozenset_type": DiagnosticCode.EXPECTED_ARRAY,
    "dict_type": DiagnosticCode.EXPECTED_OBJECT,
    "model_type": DiagnosticCode.EXPECTED_OBJECT,
    "model_attributes_type": DiagnosticCode.EXPECTED_OBJECT,
    "literal_error": DiagnosticCode.INVALID_ENUM,
    "enum": DiagnosticCode.INVALID_ENUM,
    "missing": DiagnosticCode.MISSING,
    "extra_forbidden": DiagnosticCode.UNEXPECTED_FIELD,
    "greater_than": DiagnosticCode.BELOW_MINIMUM,
    "greater_than_equal": DiagnosticCode.BELOW_MINIMUM,
    "less_than": DiagnosticCode.ABOVE_MAXIMUM,
    "less_than_equal": DiagnosticCode.ABOVE_MAXIMUM,
    "too_short": DiagnosticCode.BELOW_MINIMUM_LENGTH,
    "string_too_short": DiagnosticCode.BELOW_MINIMUM_LENGTH,
    "too_long": DiagnosticCode.ABOVE_MAXIMUM_LENGTH,
    "string_too_long": DiagnosticCode.ABOVE_MAXIMUM_LENGTH,
}


def _diagnostic(
    entry: Mapping[str, object], root_schema: Mapping[str, object]
) -> ValidationDiagnostic:
    raw_code = entry["type"]
    code = _PYDANTIC_CODES.get(raw_code) if isinstance(raw_code, str) else None
    location = entry["loc"]
    return ValidationDiagnostic(
        code=DiagnosticCode.VALIDATION_FAILED if code is None else code,
        path=_safe_path(location if isinstance(location, tuple) else (), root_schema),
    )


def validation_diagnostics(
    error: ValidationError, root_schema: Mapping[str, object]
) -> tuple[ValidationDiagnostic, ...]:
    return tuple(_diagnostic(entry, root_schema) for entry in error.errors())


def _schema_failure[T: BaseModel](
    error: ValidationError,
    contract: ResponseContract[T],
    normalization: Normalization,
) -> ResponseValidationError:
    root_schema = contract.schema
    return ResponseValidationError(
        validation_diagnostics(error, root_schema),
        normalization,
    )


def _attempt[T: BaseModel](
    raw: str, contract: ResponseContract[T], normalization: Normalization
) -> ValidatedResponse[T] | ResponseValidationError | None:
    try:
        return ValidatedResponse(contract.validate(raw), normalization)
    except ValidationError as error:
        return _schema_failure(error, contract, normalization)
    except ValueError:
        return None


def validate_response[T: BaseModel](
    raw: str, contract: ResponseContract[T]
) -> ValidatedResponse[T]:
    bare = _attempt(raw, contract, Normalization.NONE)
    if isinstance(bare, ValidatedResponse):
        return bare
    if isinstance(bare, ResponseValidationError):
        raise bare

    match = _JSON_FENCE.fullmatch(raw)
    if match is None:
        raise ResponseValidationError((ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),))
    fenced = _attempt(match.group(1), contract, Normalization.JSON_FENCE_V1)
    if isinstance(fenced, ValidatedResponse):
        return fenced
    if isinstance(fenced, ResponseValidationError):
        raise fenced
    raise ResponseValidationError(
        (ValidationDiagnostic(DiagnosticCode.INVALID_JSON, ()),),
        Normalization.JSON_FENCE_V1,
    )
