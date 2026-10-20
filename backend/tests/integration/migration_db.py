"""Disposable PostgreSQL databases for migration tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Row, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.migrations.adopt import adopt_unversioned_database
from app.migrations.catalog import SchemaSnapshot
from app.migrations.introspect import introspect_connection
from app.migrations.lock import LOCK_KEY
from app.migrations.runner import upgrade_database

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
TEST_DATABASE_URL = make_url(
    os.getenv(
        "TEST_DATABASE_URL", "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test"
    )
)

_BOOTSTRAP = """
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  registers the models of this historical commit
from app.models.base import Base


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


asyncio.run(main())
"""


@dataclass(frozen=True)
class AlembicResult:
    returncode: int
    stdout: str
    stderr: str


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stdout}\n{result.stderr}")


class DisposableDatabase:
    def __init__(self) -> None:
        self.name = f"saga_migration_{uuid.uuid4().hex}"
        self.url = TEST_DATABASE_URL.set(database=self.name).render_as_string(hide_password=False)
        self.engine: AsyncEngine | None = None

    async def __aenter__(self) -> DisposableDatabase:
        admin = create_async_engine(
            TEST_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
        )
        try:
            async with admin.connect() as conn:
                await conn.exec_driver_sql(f'CREATE DATABASE "{self.name}"')
        except BaseException:
            await admin.dispose()
            raise
        await admin.dispose()
        self.engine = create_async_engine(self.url, poolclass=NullPool)
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except BaseException:
            await self.drop()
            raise
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.drop()

    async def drop(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
        admin = create_async_engine(
            TEST_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
        )
        try:
            async with admin.connect() as conn:
                await conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{self.name}" WITH (FORCE)')
        finally:
            await admin.dispose()

    def _engine(self) -> AsyncEngine:
        assert self.engine is not None, "use the database inside its context manager"
        return self.engine

    async def run_alembic(
        self,
        *args: str,
        config_path: Path | None = None,
        database_url: str | None = None,
        timeout: float = 120,
    ) -> AlembicResult:
        env = {**os.environ, "DATABASE_URL": database_url or self.url}
        if config_path is not None:
            env["SAGA_CONFIG_PATH"] = str(config_path)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "alembic",
            *args,
            cwd=BACKEND_DIR,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.communicate()
            raise
        return AlembicResult(
            process.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )

    async def upgrade(self, revision: str = "head") -> AlembicResult:
        result = await self.run_alembic("upgrade", revision)
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    async def downgrade(self, revision: str) -> AlembicResult:
        result = await self.run_alembic("downgrade", revision)
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    async def adopt(self, profile_id: str) -> None:
        await adopt_unversioned_database(profile_id, engine=self._engine())

    async def upgrade_via_app(self, *, lock_timeout_seconds: float | None = None) -> None:
        await upgrade_database(self._engine(), lock_timeout_seconds=lock_timeout_seconds)

    async def build_frozen_schema(self, commit: str) -> None:
        with tempfile.TemporaryDirectory(prefix="saga-frozen-") as tmp:
            workdir = Path(tmp)
            archive = workdir / "source.tar"
            await asyncio.to_thread(
                _run,
                ["git", "-C", str(REPO_ROOT), "archive", commit, "-o", str(archive)],
                cwd=REPO_ROOT,
            )
            extracted = workdir / "source"
            extracted.mkdir()
            await asyncio.to_thread(
                _run, ["tar", "-xf", str(archive), "-C", str(extracted)], cwd=workdir
            )
            backend = extracted / "backend"
            script = backend / "_migration_bootstrap.py"
            script.write_text(_BOOTSTRAP, encoding="utf-8")
            try:
                await asyncio.to_thread(
                    _run,
                    [sys.executable, str(script)],
                    cwd=backend,
                    env={"DATABASE_URL": self.url},
                )
            finally:
                script.unlink(missing_ok=True)

    async def snapshot(self) -> SchemaSnapshot:
        async with self._engine().begin() as conn:
            return await conn.run_sync(introspect_connection)

    async def execute(self, sql: str, params: dict[str, object] | None = None) -> None:
        async with self._engine().begin() as conn:
            await conn.execute(text(sql), params or {})

    async def execute_autocommit(self, sql: str) -> None:
        async with self._engine().connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.exec_driver_sql(sql)

    async def fetch_one(
        self, sql: str, params: dict[str, object] | None = None
    ) -> Row[tuple[object, ...]]:
        async with self._engine().connect() as conn:
            return (await conn.execute(text(sql), params or {})).one()

    async def fetch_all(
        self, sql: str, params: dict[str, object] | None = None
    ) -> list[Row[tuple[object, ...]]]:
        async with self._engine().connect() as conn:
            return list((await conn.execute(text(sql), params or {})).all())

    async def version(self) -> str | None:
        row = await self.fetch_one("SELECT to_regclass('public.alembic_version')")
        if row[0] is None:
            return None
        return str((await self.fetch_one("SELECT version_num FROM alembic_version"))[0])

    async def table_exists(self, name: str) -> bool:
        return (await self.fetch_one("SELECT to_regclass(:name)", {"name": f"public.{name}"}))[
            0
        ] is not None

    @asynccontextmanager
    async def hold_lock(self) -> AsyncIterator[None]:
        engine = create_async_engine(self.url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                await connection.execute(
                    text("SELECT pg_advisory_lock(:high, :low)"),
                    {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
                )
                await connection.commit()
                try:
                    yield
                finally:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(:high, :low)"),
                        {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
                    )
                    await connection.commit()
        finally:
            await engine.dispose()
