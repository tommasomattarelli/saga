"""ADR 0018 point 5 — real alembic 007 upgrade from the frozen 006 baseline."""

import hashlib
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration import migration_baseline as mb


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Iterator[None]:
    mb.create_migration_database()
    try:
        mb.build_baseline_and_stamp(tmp_path_factory.mktemp("p5_baseline"))
        yield
    finally:
        mb.drop_migration_database()


async def _fetch_one(sql: str, params: dict | None = None):
    engine = create_async_engine(mb.MIGRATION_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params or {})).fetchone()
    finally:
        await engine.dispose()


async def _fetch_all(sql: str, params: dict | None = None):
    engine = create_async_engine(mb.MIGRATION_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql), params or {})).fetchall()
    finally:
        await engine.dispose()


async def _version() -> str:
    row = await _fetch_one("SELECT version_num FROM alembic_version")
    assert row is not None
    return str(row[0])


async def _ensure_upgraded() -> None:
    if await _version() != "007_embedding_index":
        mb.run_alembic(["upgrade", "007_embedding_index"])


async def test_baseline_is_the_frozen_006_schema(baseline) -> None:
    assert await _version() == "006_user_provider_settings"
    tables = {
        row[0]
        for row in await _fetch_all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    assert {"users", "campaigns", "turns", "memory_facts"} <= tables
    assert not ({"embedding_indexes", "source_embeddings"} & tables)
    legacy_types = {
        row[0]
        for row in await _fetch_all(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a"
            " JOIN pg_class c ON c.oid = a.attrelid"
            " WHERE c.relname = ANY(:tables) AND a.attname = 'embedding'",
            {"tables": ["turns", "memory_facts"]},
        )
    }
    assert legacy_types == {"vector(384)"}


async def test_upgrade_007_backfills_legacy_and_keeps_old_columns(baseline) -> None:
    mb.run_alembic(["upgrade", "007_embedding_index"])
    assert await _version() == "007_embedding_index"

    index_rows = await _fetch_all(
        "SELECT campaign_id, provider, model, endpoint_name, endpoint_identity,"
        " pipeline_version, dimension, is_active, rebuild_state FROM embedding_indexes"
    )
    assert len(index_rows) == 1
    (
        campaign_id,
        provider,
        model,
        endpoint_name,
        endpoint_identity,
        pipeline_version,
        dimension,
        is_active,
        rebuild_state,
    ) = index_rows[0]
    assert str(campaign_id) == mb.CAMPAIGN_WITH_VECTORS
    assert (provider, model, endpoint_name) == ("openai", "text-embedding-3-small", None)
    assert endpoint_identity == "https://api.openai.com/v1"
    assert (pipeline_version, dimension, is_active, rebuild_state) == (
        "embed-v1-legacy",
        384,
        True,
        "completed",
    )

    source_rows = await _fetch_all(
        "SELECT source_type, turn_id, memory_fact_id, text_hash, work_state,"
        " vector_dims(embedding) FROM source_embeddings ORDER BY source_type"
    )
    assert len(source_rows) == 2
    by_type = {row[0]: row for row in source_rows}
    turn_row = by_type["turn"]
    assert str(turn_row[1]) == mb.TURN_WITH_VECTOR
    assert turn_row[2] is None
    assert turn_row[3] == hashlib.sha256(mb.TURN_TEXT.encode()).hexdigest()
    assert turn_row[4] == "embedded"
    assert turn_row[5] == mb.LEGACY_DIMENSIONS
    fact_row = by_type["memory_fact"]
    assert str(fact_row[2]) == mb.FACT_WITH_VECTOR
    assert fact_row[1] is None
    assert fact_row[3] == hashlib.sha256(mb.FACT_TEXT.encode()).hexdigest()

    skipped = await _fetch_all(
        "SELECT count(*) FROM source_embeddings WHERE turn_id = :t OR memory_fact_id = :f",
        {"t": mb.TURN_WITHOUT_VECTOR, "f": mb.FACT_WITHOUT_VECTOR},
    )
    assert skipped[0][0] == 0

    clean_indexes = await _fetch_all(
        "SELECT count(*) FROM embedding_indexes WHERE campaign_id = :cid",
        {"cid": mb.CAMPAIGN_WITHOUT_VECTORS},
    )
    assert clean_indexes[0][0] == 0

    preserved = {
        row[0]
        for row in await _fetch_all(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a"
            " JOIN pg_class c ON c.oid = a.attrelid"
            " WHERE c.relname = ANY(:tables) AND a.attname = 'embedding'",
            {"tables": ["turns", "memory_facts"]},
        )
    }
    assert preserved == {"vector(384)"}
    legacy_vector = await _fetch_one(
        "SELECT vector_dims(embedding) FROM turns WHERE id = :t", {"t": mb.TURN_WITH_VECTOR}
    )
    assert legacy_vector[0] == mb.LEGACY_DIMENSIONS
    null_vector = await _fetch_one(
        "SELECT embedding FROM memory_facts WHERE id = :f", {"f": mb.FACT_WITHOUT_VECTOR}
    )
    assert null_vector[0] is None

    enums = {
        row[0]
        for row in await _fetch_all(
            "SELECT typname FROM pg_type WHERE typname = ANY(:names)",
            {
                "names": [
                    "embedding_rebuild_state",
                    "embedding_source_type",
                    "embedding_work_state",
                ]
            },
        )
    }
    assert enums == {"embedding_rebuild_state", "embedding_source_type", "embedding_work_state"}

    constraints = {
        row[0]
        for row in await _fetch_all(
            "SELECT conname FROM pg_constraint WHERE conname = ANY(:names)",
            {"names": ["uq_turns_id_campaign", "uq_memory_facts_id_campaign"]},
        )
    }
    assert constraints == {"uq_turns_id_campaign", "uq_memory_facts_id_campaign"}


async def test_downgrade_then_upgrade_is_representable_for_the_legacy_case(baseline) -> None:
    await _ensure_upgraded()

    mb.run_alembic(["downgrade", "006_user_provider_settings"])
    assert await _version() == "006_user_provider_settings"
    tables = {
        row[0]
        for row in await _fetch_all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    assert not ({"embedding_indexes", "source_embeddings"} & tables)
    legacy = await _fetch_one(
        "SELECT vector_dims(embedding) FROM turns WHERE id = :t", {"t": mb.TURN_WITH_VECTOR}
    )
    assert legacy[0] == mb.LEGACY_DIMENSIONS

    mb.run_alembic(["upgrade", "007_embedding_index"])
    assert await _version() == "007_embedding_index"
    sources = await _fetch_all("SELECT count(*) FROM source_embeddings")
    assert sources[0][0] == 2
