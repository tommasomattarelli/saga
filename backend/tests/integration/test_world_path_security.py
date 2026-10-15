import shutil
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.world_library import ensure_library, worlds_dir
from app.models.campaign import Campaign


@pytest.mark.asyncio
async def test_editor_rejects_external_write_before_touching_files(
    auth_client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()
    original = (worlds_dir() / "the-awakening" / "world.yaml").read_bytes()
    outside = tmp_path / "outside.yaml"
    outside.write_text("private content")
    payload = (await auth_client.get("/api/worlds/the-awakening")).json()
    payload["npcs"][0]["slug"] = str(outside.with_suffix(""))

    response = await auth_client.put("/api/worlds/the-awakening", json=payload)

    assert response.status_code == 422
    assert outside.read_text() == "private content"
    assert (worlds_dir() / "the-awakening" / "world.yaml").read_bytes() == original
    assert str(tmp_path) not in response.text


@pytest.mark.asyncio
async def test_campaign_cannot_load_world_outside_library(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()
    shutil.copytree(worlds_dir() / "the-awakening", tmp_path / "outside")

    response = await auth_client.post(
        "/api/campaigns",
        json={"world_id": "../outside", "name": "Escape", "difficulty": "medium"},
    )

    assert response.status_code == 404
    assert (await db_session.execute(select(Campaign))).scalars().all() == []
