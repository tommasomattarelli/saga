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


def test_round_trip_with_custom_npc_fields(tmp_path):
    # ADR 0009 G1/G4: declared npc_fields + flat authored custom trait survive
    # the write → load → validate cycle.
    from app.core.world_validator import validate_world

    payload = to_editable(load_world(EXAMPLE_WORLD))
    payload["taxonomy"]["npc_fields"] = [
        {"name": "role", "default": "Commoner", "scene": True},
        {"name": "honor_code", "default": "", "scene": False},
    ]
    lyra = next(n for n in payload["npcs"] if n["slug"] == "lyra")
    lyra["honor_code"] = "never lies"
    for npc in payload["npcs"]:  # drop fields the new declaration no longer allows
        for stale in ("personality", "motivation", "secret"):
            npc.pop(stale, None)

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    reloaded = load_world(target)

    assert validate_world(reloaded, max_depth=8) == []
    fields = {f.name: f for f in reloaded.taxonomy.npc_fields}
    assert fields["role"].scene is True
    assert reloaded.npcs["lyra"].descriptives()["honor_code"] == "never lies"
    assert to_editable(reloaded) == payload


def test_write_world_edit_then_reload(tmp_path):
    payload = to_editable(load_world(EXAMPLE_WORLD))
    thorn = next(n for n in payload["nodes"] if n["slug"] == "thornhaven")
    thorn["params"]["population"] = 999

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    reloaded = load_world(target)
    assert reloaded.nodes["thornhaven"].params["population"] == 999


def test_round_trip_with_authored_statblocks(tmp_path):
    # ADR 0003 B3/F: an authored statblock and a world-defined npc_class survive
    # the write → load → validate cycle, and stay out of the descriptive traits.
    from app.core.world_validator import validate_world

    payload = to_editable(load_world(EXAMPLE_WORLD))
    payload["taxonomy"]["npc_classes"] = [
        {
            "name": "commoner",
            "hp_class": "weak",
            "defense": "easy",
            "damage_class": "unarmed",
            "attack_mod": 0,
        },
        {
            "name": "warlord",
            "hp_class": "boss",
            "defense": "very_hard",
            "damage_class": "heavy",
            "attack_mod": 7,
        },
    ]
    lyra = next(n for n in payload["npcs"] if n["slug"] == "lyra")
    lyra.update({"npc_class": "warlord", "max_hp": 120, "damage_class": "heavy"})
    aldric = next(n for n in payload["npcs"] if n["slug"] == "aldric")
    aldric["npc_class"] = "commoner"  # the example authors "royale", now undeclared

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    reloaded = load_world(target)

    assert validate_world(reloaded, max_depth=8) == []
    assert {c.name for c in reloaded.taxonomy.npc_classes} == {"commoner", "warlord"}
    assert reloaded.npcs["lyra"].npc_class == "warlord"
    assert reloaded.npcs["lyra"].statblock() == {"max_hp": 120, "damage_class": "heavy"}
    assert "npc_class" not in reloaded.npcs["lyra"].descriptives()
    assert to_editable(reloaded) == payload


def test_an_undeclared_class_is_caught_on_reload(tmp_path):
    from app.core.world_validator import validate_world

    payload = to_editable(load_world(EXAMPLE_WORLD))
    payload["taxonomy"]["npc_classes"] = [{"name": "commoner"}]
    next(n for n in payload["npcs"] if n["slug"] == "aldric")["npc_class"] = "lich-emperor"

    target = tmp_path / "the-awakening"
    write_world(payload, target)
    errors = validate_world(load_world(target), max_depth=8)

    assert any("unknown npc class 'lich-emperor'" in e for e in errors)
