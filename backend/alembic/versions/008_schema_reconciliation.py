"""Frozen 007-to-008 schema reconciliation."""

import re
from typing import TypedDict

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = "008_schema_reconciliation"
down_revision = "007_embedding_index"
branch_labels = None
depends_on = None

_RETIRED_TABLES = ("achievements", "profile_stats")


class RetiredTableSchema(TypedDict):
    columns: dict[str, tuple[str, bool, str | None]]
    constraints: dict[str, str]
    indexes: dict[str, tuple[bool, str]]


_RETIRED_SCHEMA: dict[str, RetiredTableSchema] = {
    "achievements": {
        "columns": {
            "id": ("uuid", False, None),
            "user_id": ("uuid", False, None),
            "slug": ("character varying(100)", False, None),
            "name": ("character varying(200)", False, None),
            "description": ("text", False, None),
            "created_at": ("timestamp with time zone", False, "now()"),
            "updated_at": ("timestamp with time zone", False, "now()"),
        },
        "constraints": {
            "achievements_pkey": "PRIMARY KEY (id)",
            "achievements_user_id_fkey": "FOREIGN KEY (user_id) REFERENCES users(id)",
        },
        "indexes": {
            "achievements_pkey": (
                True,
                "CREATE UNIQUE INDEX achievements_pkey ON public.achievements USING btree (id)",
            ),
            "ix_achievements_user_id": (
                False,
                "CREATE INDEX ix_achievements_user_id ON public.achievements USING btree (user_id)",
            ),
        },
    },
    "profile_stats": {
        "columns": {
            "id": ("uuid", False, None),
            "user_id": ("uuid", False, None),
            "total_turns": ("integer", False, None),
            "total_campaigns": ("integer", False, None),
            "total_play_time_minutes": ("integer", False, None),
            "stats_data": ("jsonb", False, None),
            "created_at": ("timestamp with time zone", False, "now()"),
            "updated_at": ("timestamp with time zone", False, "now()"),
        },
        "constraints": {
            "profile_stats_pkey": "PRIMARY KEY (id)",
            "profile_stats_user_id_fkey": "FOREIGN KEY (user_id) REFERENCES users(id)",
        },
        "indexes": {
            "ix_profile_stats_user_id": (
                True,
                "CREATE UNIQUE INDEX ix_profile_stats_user_id"
                " ON public.profile_stats USING btree (user_id)",
            ),
            "profile_stats_pkey": (
                True,
                "CREATE UNIQUE INDEX profile_stats_pkey ON public.profile_stats USING btree (id)",
            ),
        },
    },
}


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def _column_state(
    bind: Connection, table: str, column: str
) -> tuple[str, bool, str | None] | None:
    row = bind.execute(
        sa.text(
            "SELECT format_type(a.atttypid, a.atttypmod), a.attnotnull, "
            "pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = 'public' AND c.relname = :table "
            "AND a.attname = :column AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"table": table, "column": column},
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), not bool(row[1]), _norm(row[2])


def _require_column(
    bind: Connection,
    table: str,
    column: str,
    type_name: str,
    *,
    nullable: bool,
    default: str | None,
) -> None:
    state = _column_state(bind, table, column)
    if state is None:
        raise RuntimeError(
            f"{table}.{column} is missing; refusing to reconcile an unexpected schema"
        )
    actual_type, actual_nullable, actual_default = state
    if actual_type != type_name or actual_nullable != nullable or actual_default != default:
        raise RuntimeError(
            f"{table}.{column} has {actual_type} "
            f"{'NULL' if actual_nullable else 'NOT NULL'} default={actual_default!r}; "
            f"expected {type_name} {'NULL' if nullable else 'NOT NULL'} default={default!r}"
        )


def _ensure_column(
    bind: Connection, table: str, column: str, type_name: str, *, nullable: bool
) -> None:
    state = _column_state(bind, table, column)
    if state is None:
        op.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_name}")
        return
    _require_column(bind, table, column, type_name, nullable=nullable, default=None)


def _set_timestamp_not_null(bind: Connection, column: str) -> None:
    state = _column_state(bind, "memory_facts", column)
    if state is None:
        raise RuntimeError(f"memory_facts.{column} is missing")
    type_name, nullable, default = state
    if (type_name, default) != ("timestamp with time zone", "now()"):
        raise RuntimeError(
            f"memory_facts.{column} has {type_name} default={default!r}; "
            "expected timestamp with time zone default='now()'"
        )
    if not nullable:
        return
    nulls = bind.execute(
        sa.text(f"SELECT count(*) FROM memory_facts WHERE {column} IS NULL")
    ).scalar_one()
    if nulls:
        raise RuntimeError(
            f"memory_facts.{column} has {nulls} NULL value(s); refusing to invent timestamps. "
            "Repair the rows or restore a backup before upgrading."
        )
    op.execute(f"ALTER TABLE memory_facts ALTER COLUMN {column} SET NOT NULL")


def _drop_known_default(
    bind: Connection, table: str, column: str, type_name: str, known_default: str
) -> None:
    state = _column_state(bind, table, column)
    if state is None:
        raise RuntimeError(f"{table}.{column} is missing; refusing to reconcile")
    actual_type, nullable, actual_default = state
    if actual_type != type_name or nullable:
        raise RuntimeError(
            f"{table}.{column} has {actual_type} "
            f"{'NULL' if nullable else 'NOT NULL'}; expected {type_name} NOT NULL"
        )
    if actual_default is None:
        return
    if actual_default != known_default:
        raise RuntimeError(
            f"{table}.{column} has unexpected default {actual_default!r}; "
            f"only the historical 007 default {known_default!r} may be removed"
        )
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")


def _table_exists(bind: Connection, table: str) -> bool:
    return (
        bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}).scalar()
        is not None
    )


def _table_signature(bind: Connection, table: str) -> RetiredTableSchema:
    columns = bind.execute(
        sa.text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
            "pg_get_expr(d.adbin, d.adrelid) FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = 'public' AND c.relname = :table "
            "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"
        ),
        {"table": table},
    ).fetchall()
    constraints = bind.execute(
        sa.text(
            "SELECT con.conname, pg_get_constraintdef(con.oid, true) "
            "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = :table ORDER BY con.conname"
        ),
        {"table": table},
    ).fetchall()
    indexes = bind.execute(
        sa.text(
            "SELECT ic.relname, i.indisunique, pg_get_indexdef(i.indexrelid) "
            "FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = :table ORDER BY ic.relname"
        ),
        {"table": table},
    ).fetchall()
    return {
        "columns": {str(name): (str(t), not bool(n), _norm(d)) for name, t, n, d in columns},
        "constraints": {str(name): _norm(definition) for name, definition in constraints},
        "indexes": {
            str(name): (bool(unique), _norm(definition)) for name, unique, definition in indexes
        },
    }


def _validate_retired_shape(bind: Connection, table: str) -> None:
    expected = _RETIRED_SCHEMA[table]
    actual = _table_signature(bind, table)
    if actual == expected:
        return
    for section in ("columns", "constraints", "indexes"):
        if actual[section] != expected[section]:
            raise RuntimeError(f"retired table {table} has an unexpected {section} definition")


def upgrade() -> None:
    bind = op.get_bind()
    present = [table for table in _RETIRED_TABLES if _table_exists(bind, table)]
    if present and len(present) != len(_RETIRED_TABLES):
        raise RuntimeError(f"retired tables present only partially: {present}")
    if present:
        for table in _RETIRED_TABLES:
            _validate_retired_shape(bind, table)

    _ensure_column(bind, "campaigns", "global_summary", "text", nullable=True)
    _ensure_column(bind, "campaigns", "persona_preset", "character varying(50)", nullable=True)
    _ensure_column(bind, "campaigns", "persona_xml", "text", nullable=True)

    state = _column_state(bind, "turns", "summarization_failed")
    if state is None:
        op.execute(
            "ALTER TABLE turns ADD COLUMN summarization_failed BOOLEAN NOT NULL DEFAULT false"
        )
        op.execute("ALTER TABLE turns ALTER COLUMN summarization_failed DROP DEFAULT")
    else:
        _require_column(
            bind, "turns", "summarization_failed", "boolean", nullable=False, default=None
        )

    for column in ("created_at", "updated_at"):
        _set_timestamp_not_null(bind, column)

    _drop_known_default(bind, "embedding_indexes", "is_active", "boolean", "false")
    _drop_known_default(
        bind,
        "embedding_indexes",
        "rebuild_state",
        "embedding_rebuild_state",
        "'queued'::embedding_rebuild_state",
    )
    _drop_known_default(
        bind,
        "source_embeddings",
        "work_state",
        "embedding_work_state",
        "'pending'::embedding_work_state",
    )

    for table in _RETIRED_TABLES:
        if _table_exists(bind, table):
            try:
                op.drop_table(table)
            except Exception as exc:
                raise RuntimeError(
                    f"cannot drop retired table {table} without cascading; "
                    "remove dependent objects first"
                ) from exc


def downgrade() -> None:
    raise RuntimeError(
        "008 cannot restore rows dropped from achievements/profile_stats; restore a backup"
    )
