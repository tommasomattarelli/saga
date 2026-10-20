"""Regenerate a frozen schema snapshot from a historical commit.

The runtime never calls this: profiles are committed JSON so recognition cannot
drift with the current ORM.  Regeneration is a deliberate, reviewable action:
git archive the commit, run its create_all in a disposable database, introspect
the real PostgreSQL catalogs with the current snapshot code, and write the JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATABASE_URL = "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test"
sys.path.insert(0, str(BACKEND_DIR))

if TYPE_CHECKING:
    from app.migrations.catalog import SchemaSnapshot

_BOOTSTRAP = """
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  registers every model in this commit
from app.models.base import Base


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


asyncio.run(main())
"""


def _database_url() -> tuple[URL, str, str]:
    source = make_url(os.getenv("TEST_DATABASE_URL", DEFAULT_DATABASE_URL))
    name = f"saga_profile_{uuid.uuid4().hex}"
    return source, name, source.set(database=name).render_as_string(hide_password=False)


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"{' '.join(cmd)} failed:\n{result.stdout}\n{result.stderr}")


async def _create_database(source: URL, name: str) -> None:
    admin = create_async_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        await admin.dispose()
    engine = create_async_engine(source.set(database=name))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except BaseException:
        await engine.dispose()
        await _drop_database(source, name)
        raise
    await engine.dispose()


async def _drop_database(source: URL, name: str) -> None:
    admin = create_async_engine(source.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.dispose()


async def _snapshot(database_url: str) -> SchemaSnapshot:
    from app.migrations.introspect import introspect_connection

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            return await conn.run_sync(introspect_connection)
    finally:
        await engine.dispose()


def _build_frozen_schema(commit: str, database_url: str, workdir: Path) -> None:
    archive = workdir / "source.tar"
    _run(["git", "-C", str(REPO_ROOT), "archive", commit, "-o", str(archive)], cwd=REPO_ROOT)
    extracted = workdir / "source"
    extracted.mkdir()
    _run(["tar", "-xf", str(archive), "-C", str(extracted)], cwd=workdir)
    backend = extracted / "backend"
    bootstrap = backend / "_freeze_schema_bootstrap.py"
    bootstrap.write_text(_BOOTSTRAP, encoding="utf-8")
    try:
        _run([sys.executable, str(bootstrap)], cwd=backend, env={"DATABASE_URL": database_url})
    finally:
        bootstrap.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", required=True, help="stable profile id")
    parser.add_argument("--target-revision", required=True)
    parser.add_argument("--kind", choices=("adoption", "fixture"), default="adoption")
    args = parser.parse_args()

    source, name, database_url = _database_url()
    asyncio.run(_create_database(source, name))
    try:
        with tempfile.TemporaryDirectory(prefix="saga-schema-") as tmp:
            _build_frozen_schema(args.commit, database_url, Path(tmp))
        snapshot = asyncio.run(_snapshot(database_url))
    finally:
        asyncio.run(_drop_database(source, name))

    payload = {
        "format": 2,
        "kind": args.kind,
        "profile": args.profile,
        "source_commit": args.commit,
        "target_revision": args.target_revision,
        "schema": snapshot,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output} ({len(snapshot['tables'])} tables, {len(snapshot['enums'])} enums)"
    )


if __name__ == "__main__":
    main()
