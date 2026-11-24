from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import cast

from pydantic import BaseModel, JsonValue


def _unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number.")
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}.")


def parse_json_document(raw: str) -> JsonValue:
    return cast(
        JsonValue,
        json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        ),
    )


@dataclass(frozen=True)
class ResponseContract[T: BaseModel]:
    name: str
    version: str
    model_type: type[T]
    _schema_json: str = field(init=False, repr=False, compare=False)
    _schema_hash: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("Contract name and version must not be blank.")
        schema_json = json.dumps(
            self.model_type.model_json_schema(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "_schema_json", schema_json)
        identity = json.dumps(
            {"name": self.name, "version": self.version, "schema": json.loads(schema_json)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "_schema_hash", hashlib.sha256(identity.encode()).hexdigest())

    @property
    def schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._schema_json))

    @property
    def schema_hash(self) -> str:
        return self._schema_hash

    def validate(self, raw: str) -> T:
        return self.model_type.model_validate(parse_json_document(raw), strict=True)
