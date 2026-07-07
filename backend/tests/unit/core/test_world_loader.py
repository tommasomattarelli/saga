"""ADR 0008 S1 — directory-convention world loader (D3/D3c/D5)."""

from pathlib import Path

import pytest
import yaml

from app.core.world_loader import WorldLoadError, load_world

TAXONOMY = {
    "kinds": [
        {"name": "region", "scale": "outdoor"},
        {"name": "site", "scale": "outdoor"},
        {"name": "building", "scale": "interior"},
        {"name": "room", "scale": "interior"},
    ],
    "terrains": [{"name": "road", "travel_multiplier": 0.75}],
    "travel_modes": [{"name": "foot", "speed_kmh": 4}],
}

WORLD_YAML = {
    "meta": {"name": "Test World", "author": "tests", "version": "1.0.0"},
    "kind": "region",
    "description": "A tiny test world.",
    "km_per_unit": 10,
}


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))


def make_world(tmp_path: Path) -> Path:
    root = tmp_path / "test-world"
    write(root / "world.yaml", WORLD_YAML)
    write(root / "taxonomy.yaml", TAXONOMY)
    write(
        root / "nodes" / "north" / "_node.yaml",
        {"kind": "region", "name": "North", "position": {"x": 1, "y": 2}},
    )
    write(
        root / "nodes" / "north" / "karak.yaml",
        {"kind": "site", "name": "Karak", "position": {"x": 3, "y": 2}},
    )
    write(
        root / "nodes" / "north" / "tavern" / "_node.yaml",
        {"kind": "building", "name": "Tavern"},
    )
    write(
        root / "nodes" / "north" / "tavern" / "hall.yaml",
        {"kind": "room", "name": "Hall", "exits": [{"to": "outside"}]},
    )
    return root


class TestLoadWorld:
    def test_loads_tree_with_parents(self, tmp_path):
        asset = load_world(make_world(tmp_path))
        assert asset.meta.name == "Test World"
        assert asset.root_slug == "test-world"
        assert asset.parent["north"] == "test-world"
        assert asset.parent["karak"] == "north"
        assert asset.parent["tavern"] == "north"
        assert asset.parent["hall"] == "tavern"

    def test_filename_is_slug(self, tmp_path):
        asset = load_world(make_world(tmp_path))
        assert "karak" in asset.nodes
        assert asset.nodes["karak"].slug == "karak"
        assert asset.nodes["tavern"].slug == "tavern"

    def test_root_gets_origin_position(self, tmp_path):
        asset = load_world(make_world(tmp_path))
        root = asset.nodes[asset.root_slug]
        assert (root.position.x, root.position.y) == (0, 0)
        assert root.km_per_unit == 10

    def test_missing_world_yaml_rejected(self, tmp_path):
        root = make_world(tmp_path)
        (root / "world.yaml").unlink()
        with pytest.raises(WorldLoadError, match="world.yaml"):
            load_world(root)

    def test_missing_taxonomy_rejected(self, tmp_path):
        root = make_world(tmp_path)
        (root / "taxonomy.yaml").unlink()
        with pytest.raises(WorldLoadError, match="taxonomy.yaml"):
            load_world(root)

    def test_dir_without_node_yaml_rejected(self, tmp_path):
        root = make_world(tmp_path)
        (root / "nodes" / "north" / "tavern" / "_node.yaml").unlink()
        with pytest.raises(WorldLoadError, match="_node.yaml"):
            load_world(root)

    def test_duplicate_slug_rejected(self, tmp_path):
        root = make_world(tmp_path)
        write(
            root / "nodes" / "karak.yaml",
            {"kind": "site", "name": "Other Karak", "position": {"x": 0, "y": 0}},
        )
        with pytest.raises(WorldLoadError, match="karak"):
            load_world(root)

    def test_id_field_in_file_rejected(self, tmp_path):
        root = make_world(tmp_path)
        write(
            root / "nodes" / "extra.yaml",
            {"id": "extra", "kind": "site", "name": "X", "position": {"x": 0, "y": 0}},
        )
        with pytest.raises(WorldLoadError, match="extra"):
            load_world(root)

    def test_invalid_yaml_reports_file(self, tmp_path):
        root = make_world(tmp_path)
        (root / "nodes" / "broken.yaml").write_text("kind: [unclosed")
        with pytest.raises(WorldLoadError, match="broken"):
            load_world(root)

    def test_pydantic_error_reports_file(self, tmp_path):
        root = make_world(tmp_path)
        write(root / "nodes" / "bad.yaml", {"kind": "site", "dragons": 7})
        with pytest.raises(WorldLoadError, match="bad"):
            load_world(root)

    def test_scenario_optional(self, tmp_path):
        root = make_world(tmp_path)
        assert load_world(root).scenario is None
        write(
            root / "scenario.yaml",
            {
                "opening": {
                    "narration": "You wake up.",
                    "start_location": "karak",
                },
                "initial_quests": [{"name": "Who am I?"}],
                "story_arcs": [{"name": "The Threat", "trigger": "mines"}],
            },
        )
        asset = load_world(root)
        assert asset.scenario.opening.start_location == "karak"

    def test_collections_loaded(self, tmp_path):
        root = make_world(tmp_path)
        write(
            root / "edges" / "north-karak.yaml",
            {"from": "north", "to": "karak", "mode": "foot"},
        )
        write(
            root / "encounters" / "road.yaml",
            {"dice": "1d6", "entries": [{"roll": [1, 6], "type": "event", "description": "x"}]},
        )
        write(root / "factions" / "guild.yaml", {"name": "Guild"})
        write(root / "npcs" / "marta.yaml", {"name": "Marta", "location": "karak"})
        asset = load_world(root)
        assert asset.edges["north-karak"].from_ == "north"
        assert asset.encounters["road"].dice == "1d6"
        assert asset.factions["guild"].name == "Guild"
        assert asset.npcs["marta"].location == "karak"

    def test_rulebook_dir_ignored(self, tmp_path):
        root = make_world(tmp_path)
        write(root / "rulebook" / "attributes.yaml", {"whatever": True})
        load_world(root)
