import shutil
from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.world_library import ensure_library, worlds_dir
from app.models.campaign import Campaign
from app.services import world_service


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


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [False, True])
async def test_create_normalization_and_failed_cleanup_stay_inside_library(
    auth_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid: bool,
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "private.yaml"
    sentinel.write_text("private content")
    body: dict = {"name": "../../outside"}
    if invalid:
        body["tags"] = "not a list"

    response = await auth_client.post("/api/worlds", json=body)

    assert response.status_code == (422 if invalid else 201)
    assert (worlds_dir() / "outside").exists() == (not invalid)
    assert sentinel.read_text() == "private content"
    assert str(tmp_path) not in response.text
    if not invalid:
        assert response.json()["slug"] == "outside"


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["../outside", "..\\outside", "C:\\outside", "/outside"])
async def test_save_rejects_hostile_slugs_without_copying_or_deleting_files(
    auth_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    slug: str,
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()
    original = (worlds_dir() / "the-awakening" / "world.yaml").read_bytes()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "private.yaml"
    sentinel.write_text("private content")
    payload = (await auth_client.get("/api/worlds/the-awakening")).json()

    with pytest.raises(HTTPException) as exc:
        world_service.save_world(slug, payload)

    assert exc.value.status_code == 404
    assert sentinel.read_text() == "private content"
    assert (worlds_dir() / "the-awakening" / "world.yaml").read_bytes() == original
