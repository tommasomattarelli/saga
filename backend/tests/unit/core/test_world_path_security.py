import shutil
from pathlib import Path

import pytest

from app.core import world_library
from app.core.world_loader import WorldLoadError, load_world
from app.core.world_writer import to_editable, write_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


@pytest.fixture
def payload() -> dict:
    return to_editable(load_world(EXAMPLE_WORLD))


@pytest.mark.parametrize("collection", ["nodes", "edges", "factions", "npcs", "encounters"])
@pytest.mark.parametrize(
    "slug",
    ["../../escaped", "/absolute", "..\\escaped", "C:\\escaped", "", None, 12, "con", "lpt1"],
)
def test_writer_rejects_all_unsafe_slugs_before_writing(
    tmp_path: Path, payload: dict, collection: str, slug: object
) -> None:
    if slug == "/absolute":
        slug = str(tmp_path / "absolute")
    payload[collection].append({"slug": slug, "name": "Unsafe"})
    target = tmp_path / "the-awakening"

    with pytest.raises(WorldLoadError):
        write_world(payload, target)

    assert not target.exists()


@pytest.mark.parametrize("parent", ["../outside", "/absolute", "bad\\parent", 12, {}])
def test_writer_rejects_unsafe_parent_even_for_unreachable_node(
    tmp_path: Path, payload: dict, parent: object
) -> None:
    payload["nodes"].append({"slug": "unreachable", "parent": parent})

    with pytest.raises(WorldLoadError):
        write_world(payload, tmp_path / "the-awakening")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("meta", []),
        ("root", None),
        ("taxonomy", "bad"),
        ("scenario", []),
        ("nodes", {}),
        ("npcs", [None]),
    ],
)
def test_writer_rejects_malformed_sections_before_writing(
    tmp_path: Path, payload: dict, key: str, value: object
) -> None:
    payload[key] = value

    with pytest.raises(WorldLoadError):
        write_world(payload, tmp_path / "the-awakening")

    assert list(tmp_path.iterdir()) == []


def test_writer_does_not_overwrite_external_file(tmp_path: Path, payload: dict) -> None:
    outside = tmp_path / "outside.yaml"
    outside.write_text("private")
    payload["npcs"][0]["slug"] = str(outside.with_suffix(""))

    with pytest.raises(WorldLoadError):
        write_world(payload, tmp_path / "the-awakening")

    assert outside.read_text() == "private"
    assert not (tmp_path / "the-awakening").exists()


def test_writer_rejects_unsafe_branch_node(tmp_path: Path, payload: dict) -> None:
    payload["nodes"].extend(
        [{"slug": "../../escaped", "parent": None}, {"slug": "leaf", "parent": "../../escaped"}]
    )

    with pytest.raises(WorldLoadError):
        write_world(payload, tmp_path / "the-awakening")

    assert list(tmp_path.iterdir()) == []


def test_world_root_cannot_be_a_symlink(tmp_path: Path, payload: dict) -> None:
    outside = tmp_path / "outside"
    shutil.copytree(EXAMPLE_WORLD, outside)
    original = (outside / "world.yaml").read_bytes()
    target = tmp_path / "linked-world"
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorldLoadError, match="symbolic links"):
        load_world(target)
    with pytest.raises(WorldLoadError, match="symbolic links"):
        write_world(payload, target)

    assert (outside / "world.yaml").read_bytes() == original


@pytest.mark.parametrize("linked", ["world.yaml", "taxonomy.yaml", "nodes", "npcs", "notes.txt"])
def test_loader_rejects_symlinked_world_contents(tmp_path: Path, linked: str) -> None:
    target = tmp_path / "the-awakening"
    shutil.copytree(EXAMPLE_WORLD, target)
    source = target / linked
    outside = tmp_path / "outside"
    if source.exists():
        source.rename(outside)
    else:
        outside.write_text("private")
    source.symlink_to(outside, target_is_directory=outside.is_dir())

    with pytest.raises(WorldLoadError, match="symbolic links"):
        load_world(target)


@pytest.mark.parametrize("linked", ["world.yaml", "nodes"])
def test_writer_rejects_existing_symlink_before_overwriting(
    tmp_path: Path, payload: dict, linked: str
) -> None:
    target = tmp_path / "the-awakening"
    target.mkdir()
    outside = tmp_path / "outside"
    if linked == "nodes":
        outside.mkdir()
    else:
        outside.write_text("private")
    (target / linked).symlink_to(outside, target_is_directory=outside.is_dir())

    with pytest.raises(WorldLoadError, match="symbolic links"):
        write_world(payload, target)

    assert sorted(p.name for p in target.iterdir()) == [linked]
    if outside.is_file():
        assert outside.read_text() == "private"
    else:
        assert list(outside.iterdir()) == []


@pytest.mark.parametrize("slug", ["../outside", "..\\outside", ".", "", "C:\\outside", "con"])
def test_library_lookup_rejects_unsafe_slugs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slug: str
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    world_library.ensure_library()
    shutil.copytree(EXAMPLE_WORLD, tmp_path / "outside")

    assert world_library.world_path(slug) is None


def test_library_lookup_before_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path / "not-created"))

    assert world_library.world_path("the-awakening") is None


def test_library_lookup_rejects_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    outside = tmp_path / "outside"
    shutil.copytree(EXAMPLE_WORLD, outside)

    assert world_library.world_path(str(outside)) is None


@pytest.mark.parametrize("link_manifest", [False, True])
def test_library_does_not_expose_linked_worlds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_manifest: bool
) -> None:
    monkeypatch.setenv("SAGA_HOME", str(tmp_path))
    world_library.ensure_library()
    outside = tmp_path / "outside"
    shutil.copytree(EXAMPLE_WORLD, outside)
    target = world_library.worlds_dir() / "linked-world"
    if link_manifest:
        target.mkdir()
        (target / "world.yaml").symlink_to(outside / "world.yaml")
    else:
        target.symlink_to(outside, target_is_directory=True)

    assert world_library.world_path("linked-world") is None
    assert "linked-world" not in {w["slug"] for w in world_library.list_worlds()}
