"""ADR 0008 S5 — world service: create, save (validated + committed), export/import."""

import io
import zipfile

import pytest
from fastapi import HTTPException

from app.core.world_library import ensure_library, worlds_dir
from app.core.world_loader import load_world
from app.core.world_writer import to_editable
from app.services import world_service


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()
    return tmp_path


def example_payload() -> dict:
    return to_editable(load_world(worlds_dir() / "the-awakening"))


class TestCreateWorld:
    def test_creates_from_default_taxonomy(self):
        card = world_service.create_world(
            {"name": "Nuovo Mondo", "author": "Me", "description": "Test", "tags": ["mine"]}
        )
        assert card["slug"] == "nuovo-mondo"
        asset = load_world(worlds_dir() / "nuovo-mondo")
        assert asset.meta.name == "Nuovo Mondo"
        assert asset.taxonomy.kind("site") is not None  # default taxonomy copied

    def test_slug_collision_rejected(self):
        with pytest.raises(HTTPException) as exc:
            world_service.create_world({"name": "The Awakening"})
        assert exc.value.status_code == 409

    def test_created_world_is_committed(self):
        world_service.create_world({"name": "Git World"})
        import subprocess

        log = subprocess.run(
            ["git", "-C", str(worlds_dir()), "log", "--oneline"],
            capture_output=True,
            text=True,
        ).stdout
        assert "git-world" in log


class TestSaveWorld:
    def test_valid_save_persists_and_commits(self):
        payload = example_payload()
        thorn = next(n for n in payload["nodes"] if n["slug"] == "thornhaven")
        thorn["params"]["population"] = 555
        world_service.save_world("the-awakening", payload)

        reloaded = load_world(worlds_dir() / "the-awakening")
        assert reloaded.nodes["thornhaven"].params["population"] == 555

    def test_invalid_save_rejected_and_library_untouched(self):
        payload = example_payload()
        payload["nodes"].append({"slug": "ghost", "kind": "nonexistent-kind", "name": "Ghost"})
        with pytest.raises(HTTPException) as exc:
            world_service.save_world("the-awakening", payload)
        assert exc.value.status_code == 422
        # library still loads clean
        reloaded = load_world(worlds_dir() / "the-awakening")
        assert "ghost" not in reloaded.nodes

    def test_save_removes_deleted_entities(self):
        payload = example_payload()
        payload["npcs"] = [n for n in payload["npcs"] if n["slug"] != "lyra"]
        world_service.save_world("the-awakening", payload)
        reloaded = load_world(worlds_dir() / "the-awakening")
        assert "lyra" not in reloaded.npcs

    def test_unknown_world_404(self):
        with pytest.raises(HTTPException) as exc:
            world_service.save_world("atlantis", example_payload())
        assert exc.value.status_code == 404


class TestExportImport:
    def test_export_import_round_trip(self):
        data = world_service.export_world("the-awakening")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert "the-awakening/world.yaml" in zf.namelist()

        # import under a free slug
        renamed = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(renamed, "w") as dst:
            for name in src.namelist():
                dst.writestr(name.replace("the-awakening", "imported-world"), src.read(name))
        card = world_service.import_world(renamed.getvalue())
        assert card["slug"] == "imported-world"
        assert load_world(worlds_dir() / "imported-world").meta.name == "The Awakening"

    def test_import_collision_rejected(self):
        data = world_service.export_world("the-awakening")
        with pytest.raises(HTTPException) as exc:
            world_service.import_world(data)
        assert exc.value.status_code == 409

    def test_import_invalid_zip_rejected(self):
        with pytest.raises(HTTPException) as exc:
            world_service.import_world(b"not a zip at all")
        assert exc.value.status_code == 422


class TestDeleteWorld:
    def test_delete_removes_and_commits(self):
        world_service.create_world({"name": "Doomed"})
        world_service.delete_world("doomed")
        assert not (worlds_dir() / "doomed").exists()

    def test_delete_unknown_404(self):
        with pytest.raises(HTTPException) as exc:
            world_service.delete_world("atlantis")
        assert exc.value.status_code == 404
