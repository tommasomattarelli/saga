"""Database revision and unversioned-schema inspection shared by all entry points."""

from __future__ import annotations

from dataclasses import dataclass

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.migrations.errors import (
    MigrationError,
    UnknownRevisionError,
    UnversionedSchemaError,
)


@dataclass(frozen=True)
class DatabaseState:
    revision: str | None
    revisions: tuple[str, ...]
    app_objects: tuple[str, ...]
    heads: tuple[str, ...]
    known_revisions: frozenset[str]
    revision_is_ancestor: bool
    vector_available: bool

    @property
    def head(self) -> str | None:
        return self.heads[0] if len(self.heads) == 1 else None

    @property
    def needs_upgrade(self) -> bool:
        if self.revision is None:
            return not self.app_objects
        return self.revision != self.head


def _ancestors(script: ScriptDirectory, revision: str) -> set[str]:
    seen: set[str] = set()
    pending = [revision]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        revision_obj = script.get_revision(current)
        if revision_obj is None:
            continue
        down = revision_obj.down_revision
        if isinstance(down, (tuple, list)):
            pending.extend(str(item) for item in down)
        elif down is not None:
            pending.append(str(down))
    return seen


async def inspect_state(connection: AsyncConnection, config: Config) -> DatabaseState:
    script = ScriptDirectory.from_config(config)
    heads = tuple(script.get_heads())
    known = frozenset(revision.revision for revision in script.walk_revisions())

    has_version_table = (
        await connection.execute(text("SELECT to_regclass('public.alembic_version')"))
    ).scalar() is not None
    revisions: tuple[str, ...] = ()
    if has_version_table:
        rows = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalars()
        revisions = tuple(str(row) for row in rows)

    objects = (
        (
            await connection.execute(
                text(
                    """
                    SELECT c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                      AND c.relname <> 'alembic_version'
                      AND NOT EXISTS (
                          SELECT 1 FROM pg_depend d
                          WHERE d.objid = c.oid AND d.deptype = 'e'
                      )
                    ORDER BY c.relname
                    """
                )
            )
        )
        .scalars()
        .all()
    )
    application_types = (
        (
            await connection.execute(
                text(
                    """
                    SELECT format('%I.%I', n.nspname, t.typname)
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
        )
        .scalars()
        .all()
    )

    vector_available = (
        await connection.execute(text("SELECT to_regtype('vector') IS NOT NULL"))
    ).scalar() is True

    revision = revisions[0] if len(revisions) == 1 else None
    ancestor = False
    if revision is not None and revision in known:
        head = heads[0] if len(heads) == 1 else None
        ancestor = revision == head or (head is not None and revision in _ancestors(script, head))

    return DatabaseState(
        revision=revision,
        revisions=revisions,
        app_objects=tuple(
            sorted(
                [str(name) for name in objects] + [f"type {name}" for name in application_types]
            )
        ),
        heads=heads,
        known_revisions=known,
        revision_is_ancestor=ancestor,
        vector_available=vector_available,
    )


def require_vector(state: DatabaseState) -> None:
    if not state.vector_available:
        raise MigrationError(
            "the pgvector extension is not installed; provision it before starting SAGA"
        )


def _require_single_head(state: DatabaseState) -> None:
    if len(state.heads) != 1:
        raise UnknownRevisionError(
            f"migration scripts expose {len(state.heads)} heads; exactly one is required"
        )


def _require_single_revision(state: DatabaseState) -> None:
    if len(state.revisions) > 1:
        raise UnknownRevisionError(
            f"database records {len(state.revisions)} alembic revisions; exactly one is required"
        )


def guard_upgrade(state: DatabaseState) -> None:
    _require_single_head(state)
    _require_single_revision(state)
    require_vector(state)
    if state.revision is None:
        if state.app_objects:
            sample = ", ".join(state.app_objects[:8])
            raise UnversionedSchemaError(
                "database contains application schema objects but no alembic revision"
                f" ({sample}); run python -m app.migrations.adopt --profile "
                "current_post_pr1|frozen_006"
            )
        return
    if state.revision not in state.known_revisions:
        raise UnknownRevisionError(
            f"database revision {state.revision!r} is unknown to this build; refusing to guess"
        )
    if not state.revision_is_ancestor:
        raise UnknownRevisionError(
            f"database revision {state.revision!r} is not an ancestor of {state.head!r}; "
            "refusing to migrate across branches"
        )


def guard_downgrade(state: DatabaseState) -> None:
    _require_single_head(state)
    _require_single_revision(state)
    if state.revision is None:
        raise UnknownRevisionError("database has no alembic revision to downgrade")
    if state.revision not in state.known_revisions:
        raise UnknownRevisionError(
            f"database revision {state.revision!r} is unknown to this build; refusing to guess"
        )
    if not state.revision_is_ancestor:
        raise UnknownRevisionError(
            f"database revision {state.revision!r} is not an ancestor of {state.head!r}; "
            "refusing to migrate across branches"
        )


def guard_stamp(_state: DatabaseState) -> None:
    raise MigrationError(
        "direct stamp is disabled; use validated adoption for an exact supported profile"
    )
