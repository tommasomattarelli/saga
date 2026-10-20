"""Frozen adoption profiles and exact schema comparison."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, TypedDict, TypeGuard

from app.migrations.catalog import (
    ColumnSnapshot,
    ConstraintSnapshot,
    IndexSnapshot,
    SchemaSnapshot,
    TableSnapshot,
    is_schema_snapshot,
)
from app.migrations.errors import MigrationConfigurationError, SchemaMismatchError

PROFILE_DIR = Path(__file__).with_name("profiles")
PROFILE_IDS = ("current_post_pr1", "frozen_006")


class AdoptionProfile(TypedDict):
    format: Literal[2]
    kind: Literal["adoption"]
    profile: str
    source_commit: str
    target_revision: str
    schema: SchemaSnapshot


def _is_adoption_profile(value: object, profile_id: str) -> TypeGuard[AdoptionProfile]:
    if not isinstance(value, dict) or set(value) != {
        "format",
        "kind",
        "profile",
        "source_commit",
        "target_revision",
        "schema",
    }:
        return False
    return (
        type(value["format"]) is int
        and value["format"] == 2
        and value["kind"] == "adoption"
        and value["profile"] == profile_id
        and isinstance(value["source_commit"], str)
        and isinstance(value["target_revision"], str)
        and is_schema_snapshot(value["schema"])
    )


def load_profile(profile_id: str) -> AdoptionProfile:
    if profile_id not in PROFILE_IDS:
        raise MigrationConfigurationError(
            f"unknown migration profile {profile_id!r}; choose one of {', '.join(PROFILE_IDS)}"
        )
    path = PROFILE_DIR / f"{profile_id}.json"
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationConfigurationError(
            f"cannot read frozen migration profile {profile_id!r}"
        ) from exc
    if not _is_adoption_profile(payload, profile_id):
        raise MigrationConfigurationError(f"frozen migration profile {profile_id!r} is invalid")
    return payload


def _column_description(column: ColumnSnapshot) -> str:
    nullable = "NULL" if column["nullable"] else "NOT NULL"
    default = column["default"]
    suffix = "" if default is None else f" DEFAULT {default}"
    extra = f" {column['identity']}{column['generated']}".rstrip()
    collation = "" if column["collation"] is None else f" COLLATE {column['collation']}"
    return f"{column['type']} {nullable}{suffix}{extra}{collation}".strip()


def _diff_mapping[T](
    expected: Mapping[str, T],
    actual: Mapping[str, T],
    label: str,
    describe: Callable[[T], str],
) -> list[str]:
    differences: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        if key not in actual:
            differences.append(f"{label}.{key} is missing")
        elif key not in expected:
            differences.append(f"{label}.{key} is unexpected")
        elif expected[key] != actual[key]:
            differences.append(
                f"{label}.{key} is {describe(actual[key])}, expected {describe(expected[key])}"
            )
    return differences


def _constraint_description(value: ConstraintSnapshot) -> str:
    return f"{value['kind']} {value['definition']}"


def _index_description(value: IndexSnapshot) -> str:
    return (
        f"{value['definition']} valid={value['valid']} ready={value['ready']} live={value['live']}"
    )


def diff_schema(expected: SchemaSnapshot, actual: SchemaSnapshot) -> list[str]:
    differences: list[str] = []

    expected_relations = expected["relations"]
    actual_relations = actual["relations"]
    for name in sorted(set(expected_relations) | set(actual_relations)):
        if name not in actual_relations:
            differences.append(f"{name} is missing")
        elif name not in expected_relations:
            differences.append(f"{name} is unexpected")
        elif expected_relations[name] != actual_relations[name]:
            differences.append(
                f"{name} is a {actual_relations[name]}, expected a {expected_relations[name]}"
            )

    expected_types = expected["types"]
    actual_types = actual["types"]
    differences.extend(
        _diff_mapping(expected_types, actual_types, "type", lambda value: value["kind"])
    )

    expected_enums = expected["enums"]
    actual_enums = actual["enums"]
    for name in sorted(set(expected_enums) | set(actual_enums)):
        if name not in actual_enums:
            differences.append(f"enum {name} is missing")
        elif name not in expected_enums:
            differences.append(f"enum {name} is unexpected")
        elif expected_enums[name] != actual_enums[name]:
            differences.append(
                f"enum {name} labels are {actual_enums[name]!r}, expected {expected_enums[name]!r}"
            )

    expected_tables = expected["tables"]
    actual_tables = actual["tables"]
    for table in sorted(expected_tables):
        if table not in actual_tables:
            continue
        expected_table: TableSnapshot = expected_tables[table]
        actual_table: TableSnapshot = actual_tables[table]
        differences.extend(
            _diff_mapping(
                expected_table["columns"],
                actual_table["columns"],
                f"{table} column",
                _column_description,
            )
        )
        differences.extend(
            _diff_mapping(
                expected_table["constraints"],
                actual_table["constraints"],
                f"{table} constraint",
                _constraint_description,
            )
        )
        differences.extend(
            _diff_mapping(
                expected_table["indexes"],
                actual_table["indexes"],
                f"{table} index",
                _index_description,
            )
        )
    return differences


def require_profile_match(profile: AdoptionProfile, actual: SchemaSnapshot) -> None:
    differences = diff_schema(profile["schema"], actual)
    if differences:
        raise SchemaMismatchError(str(profile["profile"]), differences)
