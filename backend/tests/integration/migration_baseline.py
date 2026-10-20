"""Machine-built pre-change 006 baseline for the ADR 0018 embedding migration.

The baseline schema must come from the immutable pre-change code at 261ad5f
(lead constraint): this helper archives that commit, runs its `create_all` from
the extracted tree, seeds the legacy 384-dim vectors the pre-change writers
produced, then uses production's validated adoption to record 006 before the
real 007 revision runs. No hand-written schema or working-tree model subtraction.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.migrations.adopt import adopt_unversioned_database

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
PRECHANGE_COMMIT = "261ad5f"

_TEST_DATABASE_URL = make_url(
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test",
    )
)
MIGRATION_DATABASE_NAME = f"saga_migration_{uuid.uuid4().hex}"
MIGRATION_DATABASE_URL = _TEST_DATABASE_URL.set(database=MIGRATION_DATABASE_NAME)
_ADMIN_DATABASE_URL = _TEST_DATABASE_URL.set(database="postgres")

LEGACY_DIMENSIONS = 384
TURN_TEXT = "The player struck and the goblin fled."
FACT_TEXT = "The goblin fled."
TURN_TEXT_NULL = "A turn whose vector was never computed."
FACT_TEXT_NULL = "A fact whose vector was never computed."

USER_ID = "11111111-1111-1111-1111-111111111111"
CAMPAIGN_WITH_VECTORS = "22222222-2222-2222-2222-222222222222"
CAMPAIGN_WITHOUT_VECTORS = "33333333-3333-3333-3333-333333333333"
TURN_WITH_VECTOR = "44444444-4444-4444-4444-444444444444"
TURN_WITHOUT_VECTOR = "55555555-5555-5555-5555-555555555555"
FACT_WITH_VECTOR = "66666666-6666-6666-6666-666666666666"
FACT_WITHOUT_VECTOR = "77777777-7777-7777-7777-777777777777"
TURN_IN_CLEAN_CAMPAIGN = "88888888-8888-8888-8888-888888888888"
FACT_IN_CLEAN_CAMPAIGN = "99999999-9999-9999-9999-999999999999"

_BASELINE_SCRIPT = """
import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  registers the pre-change models
from app.models.base import Base


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


asyncio.run(main())
"""


def _run(cmd: list[str], cwd: Path, env_extra: dict[str, str] | None = None) -> None:
    env = {**os.environ, **(env_extra or {})}
    result = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed (cwd={cwd}):\n{result.stdout}\n{result.stderr}"
        )


async def _create_migration_database() -> None:
    admin_engine = create_async_engine(_ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.exec_driver_sql(f'CREATE DATABASE "{MIGRATION_DATABASE_NAME}"')
    finally:
        await admin_engine.dispose()

    engine = create_async_engine(MIGRATION_DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except BaseException:
        await engine.dispose()
        await _drop_migration_database()
        raise
    await engine.dispose()


async def _drop_migration_database() -> None:
    engine = create_async_engine(_ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{MIGRATION_DATABASE_NAME}" WITH (FORCE)'
            )
    finally:
        await engine.dispose()


def create_migration_database() -> None:
    asyncio.run(_create_migration_database())


def drop_migration_database() -> None:
    asyncio.run(_drop_migration_database())


async def _drop_public_tables() -> None:
    engine = create_async_engine(MIGRATION_DATABASE_URL)
    async with engine.begin() as conn:
        names = (
            (
                await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            )
            .scalars()
            .all()
        )
        for name in names:
            await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
    await engine.dispose()


async def _seed_legacy_rows() -> None:
    engine = create_async_engine(MIGRATION_DATABASE_URL)
    vector = "[" + ",".join(["0.1"] * LEGACY_DIMENSIONS) + "]"

    async def insert(sql: str, params: dict[str, str]) -> None:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)

    await insert(
        "INSERT INTO users (id, username, email, hashed_password, is_active, is_admin,"
        " preferred_language) VALUES (:id, 'legacy', 'legacy@example.com', 'pw', true, false, 'en')",
        {"id": USER_ID},
    )
    for cid, name in ((CAMPAIGN_WITH_VECTORS, "A"), (CAMPAIGN_WITHOUT_VECTORS, "B")):
        await insert(
            "INSERT INTO campaigns (id, user_id, world_slug, world_version, name, status,"
            " difficulty, turn_number, character_data, world_state, quests)"
            " VALUES (:id, :uid, 'w', NULL, :name, 'ACTIVE', 'MEDIUM', 0,"
            " '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)",
            {"id": cid, "uid": USER_ID, "name": name},
        )
    await insert(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " summary, embedding, importance_score, summarization_failed)"
        " VALUES (:id, :cid, 1, 'a', 'n', 'm', :summary, (:emb)::vector, 5, false)",
        {
            "id": TURN_WITH_VECTOR,
            "cid": CAMPAIGN_WITH_VECTORS,
            "summary": TURN_TEXT,
            "emb": vector,
        },
    )
    await insert(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " summary, embedding, importance_score, summarization_failed)"
        " VALUES (:id, :cid, 2, 'a', 'n', 'm', :summary, NULL, 5, false)",
        {"id": TURN_WITHOUT_VECTOR, "cid": CAMPAIGN_WITH_VECTORS, "summary": TURN_TEXT_NULL},
    )
    await insert(
        "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type, content,"
        " embedding) VALUES (:id, :cid, 1, 'Goblin', 'npc', :content, (:emb)::vector)",
        {
            "id": FACT_WITH_VECTOR,
            "cid": CAMPAIGN_WITH_VECTORS,
            "content": FACT_TEXT,
            "emb": vector,
        },
    )
    await insert(
        "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type, content,"
        " embedding) VALUES (:id, :cid, 2, 'Goblin', 'npc', :content, NULL)",
        {"id": FACT_WITHOUT_VECTOR, "cid": CAMPAIGN_WITH_VECTORS, "content": FACT_TEXT_NULL},
    )
    await insert(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " summary, embedding, importance_score, summarization_failed)"
        " VALUES (:id, :cid, 1, 'a', 'n', 'm', :summary, NULL, 5, false)",
        {"id": TURN_IN_CLEAN_CAMPAIGN, "cid": CAMPAIGN_WITHOUT_VECTORS, "summary": TURN_TEXT_NULL},
    )
    await insert(
        "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type, content,"
        " embedding) VALUES (:id, :cid, 1, 'Empty', 'npc', :content, NULL)",
        {"id": FACT_IN_CLEAN_CAMPAIGN, "cid": CAMPAIGN_WITHOUT_VECTORS, "content": FACT_TEXT_NULL},
    )
    await engine.dispose()


def run_alembic(args: list[str]) -> None:
    _run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env_extra={"DATABASE_URL": MIGRATION_DATABASE_URL.render_as_string(hide_password=False)},
    )


def build_baseline_and_adopt(workdir: Path) -> None:
    """Rebuild the migration database at the frozen 006 baseline, seeded."""
    asyncio.run(_drop_public_tables())

    archive = workdir / "prechange.tar"
    _run(
        ["git", "-C", str(REPO_ROOT), "archive", PRECHANGE_COMMIT, "-o", str(archive)],
        cwd=REPO_ROOT,
    )
    extracted_backend = workdir / "code" / "backend"
    extracted_backend.mkdir(parents=True)
    _run(["tar", "-xf", str(archive), "-C", str(workdir / "code")], cwd=workdir)

    script_path = extracted_backend / "_p5_baseline.py"
    script_path.write_text(_BASELINE_SCRIPT, encoding="utf-8")
    _run(
        [sys.executable, str(script_path)],
        cwd=extracted_backend,
        env_extra={"DATABASE_URL": MIGRATION_DATABASE_URL.render_as_string(hide_password=False)},
    )
    script_path.unlink()

    asyncio.run(_seed_legacy_rows())
    asyncio.run(_adopt_frozen_baseline())


async def _adopt_frozen_baseline() -> None:
    engine = create_async_engine(MIGRATION_DATABASE_URL)
    try:
        await adopt_unversioned_database("frozen_006", engine=engine)
    finally:
        await engine.dispose()
