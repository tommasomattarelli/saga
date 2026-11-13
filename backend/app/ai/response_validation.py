from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ValidationError

from app.ai.response_contracts import ResponseContract

_JSON_FENCE = re.compile(
    r"\A[ \t\r\n]*```json(?:\r\n|\n)(.*?)(?:\r\n|\n)```[ \t\r\n]*\Z", re.DOTALL
)
_KNOWN_ERROR_CODES = {
    "bool_type",
    "extra_forbidden",
    "float_type",
    "int_type",
    "literal_error",
    "missing",
    "string_type",
}


class Normalization(StrEnum):
    NONE = "none"
    JSON_FENCE_V1 = "json_fence_v1"


@dataclass(frozen=True)
class ValidationDiagnostic:
    code: str
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


def _resolve_schema(schema: object, root: Mapping[str, object]) -> dict[str, object]:
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


def _safe_path(
    location: tuple[object, ...], root_schema: Mapping[str, object]
) -> tuple[str | int, ...]:
    path: list[str | int] = []
    schema = root_schema
    for segment in location:
        schema = _resolve_schema(schema, root_schema)
        properties = schema.get("properties")
        additional_properties = schema.get("additionalProperties")
        if isinstance(segment, str) and isinstance(properties, dict) and segment in properties:
            path.append(segment)
            child = properties[segment]
        elif isinstance(additional_properties, dict):
            path.append("<unknown>")
            child = additional_properties
        elif isinstance(segment, int) and "items" in schema:
            path.append(segment)
            child = schema["items"]
        elif isinstance(segment, str):
            path.append("<unknown>")
            child = {}
        else:
            path.append("<unknown>")
            child = {}
        schema = child if isinstance(child, dict) else {}
    return tuple(path)


def _schema_failure[T: BaseModel](
    error: ValidationError,
    contract: ResponseContract[T],
    normalization: Normalization,
) -> ResponseValidationError:
    root_schema = contract.schema
    diagnostics = tuple(
        ValidationDiagnostic(
            code=(entry["type"] if entry["type"] in _KNOWN_ERROR_CODES else "validation_failed"),
            path=_safe_path(entry["loc"], root_schema),
        )
        for entry in error.errors()
    )
    return ResponseValidationError(diagnostics, normalization)


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
        raise ResponseValidationError((ValidationDiagnostic("invalid_json", ()),))
    fenced = _attempt(match.group(1), contract, Normalization.JSON_FENCE_V1)
    if isinstance(fenced, ValidatedResponse):
        return fenced
    if isinstance(fenced, ResponseValidationError):
        raise fenced
    raise ResponseValidationError(
        (ValidationDiagnostic("invalid_json", ()),), Normalization.JSON_FENCE_V1
    )
