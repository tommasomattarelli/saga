"""Freeze checks: historical catalogs and the empty-database chain converge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.migrations.profiles import diff_schema, load_profile, require_profile_match
from tests.integration.migration_db import DisposableDatabase

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRE_001_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "schema_pre_001.json"

CURRENT_COMMIT = "5e9206da28a0be1d8e669dcc72ed0af6a3525eac"
FROZEN_006_COMMIT = "261ad5fb53003844efbe1d8097d9393469686291"
PRE_001_COMMIT = "94db17df4baf8c0116227dffc3e508308693f00d"


@pytest.mark.parametrize(
    ("commit", "profile_id"),
    [
        (CURRENT_COMMIT, "current_post_pr1"),
        (FROZEN_006_COMMIT, "frozen_006"),
    ],
)
async def test_committed_profile_matches_its_frozen_create_all(
    commit: str, profile_id: str
) -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(commit)
        profile = load_profile(profile_id)
        require_profile_match(profile, await database.snapshot())


async def test_pre_001_fixture_matches_frozen_create_all() -> None:
    fixture = json.loads(PRE_001_FIXTURE.read_text(encoding="utf-8"))
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(PRE_001_COMMIT)
        assert diff_schema(fixture["schema"], await database.snapshot()) == []


async def test_empty_database_chain_converges_on_current_profile() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        assert await database.version() == "009_campaign_language"
        await database.require_head_schema()


async def test_pre_001_revision_matches_its_fixture() -> None:
    fixture = json.loads(PRE_001_FIXTURE.read_text(encoding="utf-8"))
    async with DisposableDatabase() as database:
        await database.upgrade("000_pre_001_schema")
        assert diff_schema(fixture["schema"], await database.snapshot()) == []


async def test_008_retires_the_legacy_meta_tables() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        assert not await database.table_exists("achievements")
        assert not await database.table_exists("profile_stats")
