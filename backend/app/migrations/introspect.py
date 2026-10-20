"""Catalog snapshot used to freeze and compare application schemas.

The snapshot deliberately excludes Alembic's own table and any object owned by
an extension: adoption validates the application schema, not provisioned
infrastructure.  Callers must run this inside a transaction because the
search_path is set transaction-locally so pg_get_* definitions stay stable.
"""

from __future__ import annotations

import re
from typing import Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.migrations.catalog import (
    ColumnSnapshot,
    ConstraintKind,
    ConstraintSnapshot,
    IndexSnapshot,
    RelationKind,
    SchemaSnapshot,
    TableSnapshot,
    TypeKind,
    TypeSnapshot,
)

SNAPSHOT_FORMAT: Literal[2] = 2
_EXCLUDED_RELATIONS = {"alembic_version"}
_RELKINDS: dict[str, RelationKind] = {
    "r": "table",
    "p": "partitioned_table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
    "S": "sequence",
}
_CONSTRAINT_TYPES: dict[str, ConstraintKind] = {
    "p": "primary_key",
    "u": "unique",
    "f": "foreign_key",
    "c": "check",
    "x": "exclusion",
}
_TYPE_KINDS: dict[str, TypeKind] = {
    "b": "base",
    "c": "composite",
    "d": "domain",
    "e": "enum",
    "r": "range",
    "m": "multirange",
}


def _normalize_sql(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip().rstrip(";") or None


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        value = value.decode()
    text_value = str(value)
    return "" if text_value == "\x00" else text_value


def _relation_rows(connection: Connection) -> list[tuple[str, RelationKind]]:
    rows = connection.execute(
        text(
            """
            SELECT c.relname, c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
              AND NOT EXISTS (
                  SELECT 1 FROM pg_depend d
                  WHERE d.objid = c.oid AND d.deptype = 'e'
              )
            ORDER BY c.relname
            """
        )
    )
    result: list[tuple[str, RelationKind]] = []
    for name, kind in rows:
        text_name = _as_text(name)
        if text_name not in _EXCLUDED_RELATIONS:
            result.append((text_name, _RELKINDS[_as_text(kind)]))
    return result


def _column_rows(connection: Connection) -> dict[str, dict[str, ColumnSnapshot]]:
    rows = connection.execute(
        text(
            """
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod),
                   a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
                   a.attidentity, a.attgenerated, a.attnum,
                   CASE WHEN a.attcollation = 0 THEN NULL
                        ELSE format('%I.%I', cn.nspname, coll.collname) END
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
            LEFT JOIN pg_collation coll ON coll.oid = a.attcollation
            LEFT JOIN pg_namespace cn ON cn.oid = coll.collnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND c.relname <> 'alembic_version'
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY c.relname, a.attnum
            """
        )
    )
    columns: dict[str, dict[str, ColumnSnapshot]] = {}
    for relname, name, type_name, not_null, default, identity, generated, _, collation in rows:
        columns.setdefault(str(relname), {})[str(name)] = {
            "type": str(type_name),
            "nullable": not bool(not_null),
            "default": _normalize_sql(default),
            "identity": _as_text(identity or ""),
            "generated": _as_text(generated or ""),
            "collation": str(collation) if collation is not None else None,
        }
    return columns


def _constraint_rows(connection: Connection) -> dict[str, dict[str, ConstraintSnapshot]]:
    rows = connection.execute(
        text(
            """
            SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid, true)
            FROM pg_constraint con
            JOIN pg_class c ON c.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname <> 'alembic_version'
            ORDER BY c.relname, con.conname
            """
        )
    )
    constraints: dict[str, dict[str, ConstraintSnapshot]] = {}
    for relname, name, kind, definition in rows:
        constraints.setdefault(str(relname), {})[str(name)] = {
            "kind": _CONSTRAINT_TYPES[_as_text(kind)],
            "definition": _normalize_sql(definition),
        }
    return constraints


def _index_rows(connection: Connection) -> dict[str, dict[str, IndexSnapshot]]:
    rows = connection.execute(
        text(
            """
            SELECT c.relname, ic.relname, i.indisunique, i.indisprimary, am.amname,
                   pg_get_expr(i.indpred, i.indrelid), pg_get_indexdef(i.indexrelid),
                   i.indisvalid, i.indisready, i.indislive
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_class ic ON ic.oid = i.indexrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_am am ON am.oid = ic.relam
            WHERE n.nspname = 'public'
              AND c.relname <> 'alembic_version'
            ORDER BY c.relname, ic.relname
            """
        )
    )
    indexes: dict[str, dict[str, IndexSnapshot]] = {}
    for relname, name, unique, primary, method, predicate, definition, valid, ready, live in rows:
        indexes.setdefault(str(relname), {})[str(name)] = {
            "unique": bool(unique),
            "primary": bool(primary),
            "method": str(method),
            "predicate": _normalize_sql(predicate),
            "definition": _normalize_sql(definition),
            "valid": bool(valid),
            "ready": bool(ready),
            "live": bool(live),
        }
    return indexes


def _type_rows(connection: Connection) -> dict[str, TypeSnapshot]:
    rows = connection.execute(
        text(
            """
            SELECT format('%I.%I', n.nspname, t.typname), t.typtype
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public'
              AND t.typtype IN ('b', 'c', 'd', 'e', 'r', 'm')
              AND t.typelem = 0
              AND NOT EXISTS (
                  SELECT 1 FROM pg_depend d
                  WHERE d.objid = t.oid AND d.deptype = 'e'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM pg_class c
                  WHERE c.oid = t.typrelid AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
              )
            ORDER BY n.nspname, t.typname
            """
        )
    )
    return {str(name): {"kind": _TYPE_KINDS[_as_text(kind)]} for name, kind in rows}


def _enum_rows(connection: Connection) -> dict[str, list[str]]:
    rows = connection.execute(
        text(
            """
            SELECT t.typname, e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public'
              AND NOT EXISTS (
                  SELECT 1 FROM pg_depend d
                  WHERE d.objid = t.oid AND d.deptype = 'e'
              )
            ORDER BY t.typname, e.enumsortorder
            """
        )
    )
    enums: dict[str, list[str]] = {}
    for name, label in rows:
        enums.setdefault(f"public.{name}", []).append(str(label))
    return enums


def introspect_connection(connection: Connection) -> SchemaSnapshot:
    connection.exec_driver_sql("SET LOCAL search_path TO public")
    relations = {f"public.{name}": kind for name, kind in _relation_rows(connection)}
    columns = _column_rows(connection)
    constraints = _constraint_rows(connection)
    indexes = _index_rows(connection)
    tables: dict[str, TableSnapshot] = {}
    for qualified, kind in relations.items():
        name = qualified.removeprefix("public.")
        if kind in {"table", "partitioned_table"}:
            tables[qualified] = {
                "columns": columns.get(name, {}),
                "constraints": constraints.get(name, {}),
                "indexes": indexes.get(name, {}),
            }
    return {
        "format": SNAPSHOT_FORMAT,
        "relations": relations,
        "types": _type_rows(connection),
        "enums": _enum_rows(connection),
        "tables": tables,
    }
