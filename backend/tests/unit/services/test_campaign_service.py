"""ADR 0008 S2 — load_valid_world: library lookup + full validation gate."""

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from app.services.campaign_service import load_valid_world


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    return tmp_path


def test_example_world_loads_valid():
    asset = load_valid_world("the-awakening")
    assert asset.root_slug == "the-awakening"


def test_unknown_world_raises_404():
    with pytest.raises(HTTPException) as exc:
        load_valid_world("atlantis")
    assert exc.value.status_code == 404


def test_broken_world_raises_422(tmp_home: Path):
    load_valid_world("the-awakening")  # seeds the library
    broken = tmp_home / "worlds" / "broken-world"
    broken.mkdir(parents=True)
    (broken / "world.yaml").write_text(yaml.safe_dump({"meta": {"name": "B"}, "kind": "world"}))
    # taxonomy.yaml missing → tier-1 load failure
    with pytest.raises(HTTPException) as exc:
        load_valid_world("broken-world")
    assert exc.value.status_code == 422


def test_invalid_references_raise_422(tmp_home: Path):
    load_valid_world("the-awakening")
    world = tmp_home / "worlds" / "the-awakening"
    (world / "npcs" / "ghost.yaml").write_text(
        yaml.safe_dump({"name": "Ghost", "location": "nowhere-real"})
    )
    with pytest.raises(HTTPException) as exc:
        load_valid_world("the-awakening")
    assert exc.value.status_code == 422
    assert any("nowhere-real" in e for e in exc.value.detail["errors"])
