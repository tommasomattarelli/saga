"""ADR 0008 S5 — world writer: editable payload ⇄ YAML tree round-trip (I6)."""

from pathlib import Path

from app.core.world_loader import load_world
from app.core.world_writer import to_editable, write_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


def test_to_editable_carries_the_full_surface():
    payload = to_editable(load_world(EXAMPLE_WORLD))
    assert payload["meta"]["name"] == "The Awakening"
    assert payload["root"]["kind"] == "world"
    slugs = {n["slug"] for n in payload["nodes"]}
    assert {"verdant-reach", "thornhaven", "common-room"} <= slugs
    thorn = next(n for n in payload["nodes"] if n["slug"] == "thornhaven")
    assert thorn["parent"] == "verdant-reach"
    assert {e["slug"] for e in payload["edges"]} == {"forest-path", "north-road"}
    assert payload["scenario"]["opening"]["start_location"] == "shrine-of-first-light"
    assert any(k["name"] == "site" for k in payload["taxonomy"]["kinds"])
    assert {f["slug"] for f in payload["factions"]} == {"thornhaven-council", "the-hollow"}
    assert {n["slug"] for n in payload["npcs"]} == {"marta", "aldric", "lyra"}
    assert {e["slug"] for e in payload["encounters"]} == {"north-road-encounters"}


def test_write_world_round_trips(tmp_path):
    original = load_world(EXAMPLE_WORLD)
    payload = to_editable(original)

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    reloaded = load_world(target)

    assert to_editable(reloaded) == payload


def test_write_world_builds_dirs_only_where_needed(tmp_path):
    payload = to_editable(load_world(EXAMPLE_WORLD))
    target = tmp_path / "the-awakening"
    write_world(payload, target)

    # node with children = dir + _node.yaml; leaf = single file (D3/D5)
    assert (target / "nodes" / "verdant-reach" / "_node.yaml").is_file()
    assert (target / "nodes" / "verdant-reach" / "shrine-of-first-light.yaml").is_file()
    assert (
        target / "nodes" / "verdant-reach" / "thornhaven" / "gilded-tankard" / "cellar.yaml"
    ).is_file()
    assert not (target / "nodes" / "verdant-reach" / "old-mines").is_dir()


def test_write_world_edit_then_reload(tmp_path):
    payload = to_editable(load_world(EXAMPLE_WORLD))
    thorn = next(n for n in payload["nodes"] if n["slug"] == "thornhaven")
    thorn["params"]["population"] = 999

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    reloaded = load_world(target)
    assert reloaded.nodes["thornhaven"].params["population"] == 999
