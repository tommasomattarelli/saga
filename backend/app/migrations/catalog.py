"""Typed frozen PostgreSQL catalog records and JSON-boundary validation."""

from __future__ import annotations

from typing import Literal, TypedDict, TypeGuard

RelationKind = Literal[
    "table", "partitioned_table", "view", "materialized_view", "foreign_table", "sequence"
]
TypeKind = Literal["base", "composite", "domain", "enum", "range", "multirange"]
ConstraintKind = Literal["primary_key", "unique", "foreign_key", "check", "exclusion"]


class ColumnSnapshot(TypedDict):
    type: str
    nullable: bool
    default: str | None
    identity: str
    generated: str
    collation: str | None


class ConstraintSnapshot(TypedDict):
    kind: ConstraintKind
    definition: str | None


class TypeSnapshot(TypedDict):
    kind: TypeKind


class IndexSnapshot(TypedDict):
    unique: bool
    primary: bool
    method: str
    predicate: str | None
    definition: str | None
    valid: bool
    ready: bool
    live: bool


class TableSnapshot(TypedDict):
    columns: dict[str, ColumnSnapshot]
    constraints: dict[str, ConstraintSnapshot]
    indexes: dict[str, IndexSnapshot]


class SchemaSnapshot(TypedDict):
    format: Literal[2]
    relations: dict[str, RelationKind]
    types: dict[str, TypeSnapshot]
    enums: dict[str, list[str]]
    tables: dict[str, TableSnapshot]


def _mapping(value: object, keys: set[str] | None = None) -> TypeGuard[dict[str, object]]:
    return (
        isinstance(value, dict)
        and all(isinstance(key, str) for key in value)
        and (keys is None or set(value) == keys)
    )


def _text_or_none(value: object) -> bool:
    return value is None or isinstance(value, str)


def is_schema_snapshot(value: object) -> TypeGuard[SchemaSnapshot]:
    if not _mapping(value, {"format", "relations", "types", "enums", "tables"}):
        return False
    if type(value["format"]) is not int or value["format"] != 2:
        return False
    if not _mapping(value["relations"]):
        return False
    if any(
        not isinstance(name, str)
        or not isinstance(kind, str)
        or kind
        not in {
            "table",
            "partitioned_table",
            "view",
            "materialized_view",
            "foreign_table",
            "sequence",
        }
        for name, kind in value["relations"].items()
    ):
        return False
    if not _mapping(value["types"]):
        return False
    for name, type_info in value["types"].items():
        if not isinstance(name, str) or not _mapping(type_info, {"kind"}):
            return False
        if not isinstance(type_info["kind"], str) or type_info["kind"] not in {
            "base",
            "composite",
            "domain",
            "enum",
            "range",
            "multirange",
        }:
            return False
    if not _mapping(value["enums"]) or any(
        not isinstance(name, str)
        or not isinstance(labels, list)
        or any(not isinstance(label, str) for label in labels)
        for name, labels in value["enums"].items()
    ):
        return False
    if not _mapping(value["tables"]):
        return False
    for name, table in value["tables"].items():
        if not isinstance(name, str) or not _mapping(table, {"columns", "constraints", "indexes"}):
            return False
        if not _mapping(table["columns"]):
            return False
        for column_name, column in table["columns"].items():
            if not isinstance(column_name, str) or not _mapping(
                column, {"type", "nullable", "default", "identity", "generated", "collation"}
            ):
                return False
            if (
                not isinstance(column["type"], str)
                or type(column["nullable"]) is not bool
                or not _text_or_none(column["default"])
                or not isinstance(column["identity"], str)
                or not isinstance(column["generated"], str)
                or not _text_or_none(column["collation"])
            ):
                return False
        if not _mapping(table["constraints"]):
            return False
        for constraint_name, constraint in table["constraints"].items():
            if not isinstance(constraint_name, str) or not _mapping(
                constraint, {"kind", "definition"}
            ):
                return False
            if (
                not isinstance(constraint["kind"], str)
                or constraint["kind"]
                not in {
                    "primary_key",
                    "unique",
                    "foreign_key",
                    "check",
                    "exclusion",
                }
                or not _text_or_none(constraint["definition"])
            ):
                return False
        if not _mapping(table["indexes"]):
            return False
        for index_name, index in table["indexes"].items():
            if not isinstance(index_name, str) or not _mapping(
                index,
                {
                    "unique",
                    "primary",
                    "method",
                    "predicate",
                    "definition",
                    "valid",
                    "ready",
                    "live",
                },
            ):
                return False
            if (
                any(
                    type(index[key]) is not bool
                    for key in ("unique", "primary", "valid", "ready", "live")
                )
                or not isinstance(index["method"], str)
                or not _text_or_none(index["predicate"])
                or not _text_or_none(index["definition"])
            ):
                return False
    return True
