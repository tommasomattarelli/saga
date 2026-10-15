import io
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.world_library import ensure_library, worlds_dir
from app.services import world_service


@pytest.fixture(autouse=True)
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    ensure_library()


def archive_with(extra: str, mode: int = 0) -> bytes:
    exported = world_service.export_world("the-awakening")
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(exported)) as source, zipfile.ZipFile(buffer, "w") as target:
        for name in source.namelist():
            target.writestr(
                name.replace("the-awakening/", "imported-world/", 1), source.read(name)
            )
        entry = zipfile.ZipInfo(extra)
        entry.create_system = 3
        entry.external_attr = mode << 16
        target.writestr(entry, b"private content")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "name",
    [
        "../escaped.txt",
        "/absolute.txt",
        "C:/escaped.txt",
        "C:escaped.txt",
        "imported-world/../escaped.txt",
        "imported-world/./notes.txt",
        "imported-world//notes.txt",
        "imported-world\\notes.txt",
        "imported-world/notes.txt:stream",
        "imported-world/NUL.txt",
        "imported-world/NUL .txt",
        "imported-world/CON .txt",
        "imported-world/AUX  .pdf",
        "imported-world/COM1 .txt",
        "imported-world/nested./notes.txt",
        "imported-world/nested /notes.txt",
    ],
)
def test_import_rejects_unsafe_archive_paths(name: str) -> None:
    data = archive_with(name)

    with pytest.raises(HTTPException) as exc:
        world_service.import_world(data)

    assert exc.value.status_code == 422
    assert not (worlds_dir() / "imported-world").exists()


def test_import_rejects_symlink_members() -> None:
    data = archive_with("imported-world/linked.txt", stat.S_IFLNK | 0o777)

    with pytest.raises(HTTPException) as exc:
        world_service.import_world(data)

    assert exc.value.status_code == 422
    assert not (worlds_dir() / "imported-world").exists()


def test_import_preserves_valid_attachments() -> None:
    data = archive_with("imported-world/Map Assets/Città_01.txt")
    world_service.import_world(data)

    assert (
        worlds_dir() / "imported-world/Map Assets/Città_01.txt"
    ).read_bytes() == b"private content"


def test_import_preserves_explicit_directory_entries() -> None:
    data = archive_with("imported-world/Empty Folder/", stat.S_IFDIR | 0o755)
    world_service.import_world(data)

    assert (worlds_dir() / "imported-world/Empty Folder").is_dir()


def test_create_rejects_windows_device_name() -> None:
    with pytest.raises(HTTPException) as exc:
        world_service.create_world({"name": "CON"})

    assert exc.value.status_code == 422
    assert not (worlds_dir() / "con").exists()


@pytest.mark.parametrize(
    "operation", [world_service.export_world, world_service.get_editable_world]
)
def test_service_rejects_linked_attachment(
    tmp_path: Path, operation: Callable[[str], object]
) -> None:
    outside = tmp_path / "private.txt"
    outside.write_text("private content")
    (worlds_dir() / "the-awakening" / "notes.txt").symlink_to(outside)

    with pytest.raises(HTTPException) as exc:
        operation("the-awakening")

    assert exc.value.status_code == 422
    assert "private content" not in str(exc.value.detail)
    assert str(tmp_path) not in str(exc.value.detail)
