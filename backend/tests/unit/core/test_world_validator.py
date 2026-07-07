"""ADR 0008 S1 — tier-3 referential integrity + dynamic param validation (I4/E2)."""

from pathlib import Path

import pytest
import yaml

from app.core.world_loader import load_world
from app.core.world_validator import validate_world

TAXONOMY = {
    "kinds": [
        {"name": "region", "scale": "outdoor"},
        {
            "name": "city",
            "scale": "outdoor",
            "params": [
                {"name": "population", "type": "int", "required": True, "min": 0},
                {"name": "mood", "type": "str"},
            ],
        },
        {"name": "building", "scale": "interior"},
        {"name": "room", "scale": "interior"},
    ],
    "terrains": [
        {"name": "road", "travel_multiplier": 0.75},
        {"name": "swamp", "travel_multiplier": 2.0},
    ],
    "travel_modes": [{"name": "foot", "speed_kmh": 4}],
    "defaults": {"terrain": "road"},
}


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))


@pytest.fixture
def world_dir(tmp_path) -> Path:
    root = tmp_path / "w"
    write(root / "world.yaml", {"meta": {"name": "W"}, "kind": "region"})
    write(root / "taxonomy.yaml", TAXONOMY)
    write(
        root / "nodes" / "karak.yaml",
        {
            "kind": "city",
            "name": "Karak",
            "position": {"x": 1, "y": 1},
            "params": {"population": 4000},
        },
    )
    write(root / "nodes" / "tavern" / "_node.yaml", {"kind": "building", "name": "Tavern"})
    write(
        root / "nodes" / "tavern" / "hall.yaml",
        {"kind": "room", "name": "Hall", "exits": [{"to": "cellar"}, {"to": "outside"}]},
    )
    write(root / "nodes" / "tavern" / "cellar.yaml", {"kind": "room", "name": "Cellar"})
    return root


def errors_of(root: Path, max_depth: int = 8) -> list[str]:
    return validate_world(load_world(root), max_depth=max_depth)


class TestValidWorld:
    def test_green_world_has_no_errors(self, world_dir):
        assert errors_of(world_dir) == []


class TestNpcPsychology:
    # ADR 0005 C3 — authored seeds validated against the (default or world) axes.
    def test_valid_seed_against_default_axes(self, world_dir):
        write(world_dir / "npcs" / "kira.yaml", {"name": "Kira", "psychology": {"trust": -30}})
        assert errors_of(world_dir) == []

    def test_unknown_axis_rejected(self, world_dir):
        write(world_dir / "npcs" / "kira.yaml", {"name": "Kira", "psychology": {"honor": 5}})
        assert any("unknown psychology axis 'honor'" in e for e in errors_of(world_dir))

    def test_value_outside_axis_range_rejected(self, world_dir):
        write(world_dir / "npcs" / "kira.yaml", {"name": "Kira", "psychology": {"trust": 500}})
        assert any("outside range" in e for e in errors_of(world_dir))

    def test_world_defined_axes_override_default(self, world_dir):
        taxonomy = {
            **TAXONOMY,
            "psychology": {
                "axes": {
                    "honor": {
                        "range": [-50, 50],
                        "default": 0,
                        "bands": [{"min": -50, "label": "shamed"}, {"min": 0, "label": "honored"}],
                    }
                }
            },
        }
        write(world_dir / "taxonomy.yaml", taxonomy)
        write(world_dir / "npcs" / "kira.yaml", {"name": "Kira", "psychology": {"honor": 40}})
        assert errors_of(world_dir) == []
        write(world_dir / "npcs" / "kira.yaml", {"name": "Kira", "psychology": {"trust": 10}})
        assert any("unknown psychology axis 'trust'" in e for e in errors_of(world_dir))


class TestStructuralRules:
    def test_unknown_kind(self, world_dir):
        write(world_dir / "nodes" / "x.yaml", {"kind": "castle", "name": "X"})
        assert any("castle" in e for e in errors_of(world_dir))

    def test_outdoor_requires_position(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {"kind": "city", "name": "X", "params": {"population": 1}},
        )
        assert any("position" in e for e in errors_of(world_dir))

    def test_interior_must_not_have_position(self, world_dir):
        write(
            world_dir / "nodes" / "tavern" / "attic.yaml",
            {"kind": "room", "name": "Attic", "position": {"x": 1, "y": 1}},
        )
        assert any("attic" in e for e in errors_of(world_dir))

    def test_interior_cannot_contain_outdoor(self, world_dir):
        write(
            world_dir / "nodes" / "tavern" / "yard" / "_node.yaml",
            {
                "kind": "city",
                "name": "Yard",
                "position": {"x": 0, "y": 0},
                "params": {"population": 1},
            },
        )
        assert any("yard" in e for e in errors_of(world_dir))

    def test_max_depth_enforced(self, world_dir):
        assert errors_of(world_dir, max_depth=1) != []

    def test_unknown_terrain_on_node(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {
                "kind": "city",
                "name": "X",
                "position": {"x": 0, "y": 0},
                "terrain": "lava",
                "params": {"population": 1},
            },
        )
        assert any("lava" in e for e in errors_of(world_dir))


class TestParamRules:
    def test_missing_required_param(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {"kind": "city", "name": "X", "position": {"x": 0, "y": 0}},
        )
        assert any("population" in e for e in errors_of(world_dir))

    def test_param_wrong_type(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {
                "kind": "city",
                "name": "X",
                "position": {"x": 0, "y": 0},
                "params": {"population": "many"},
            },
        )
        assert any("population" in e for e in errors_of(world_dir))

    def test_param_below_min(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {
                "kind": "city",
                "name": "X",
                "position": {"x": 0, "y": 0},
                "params": {"population": -5},
            },
        )
        assert any("population" in e for e in errors_of(world_dir))

    def test_undeclared_param_rejected(self, world_dir):
        write(
            world_dir / "nodes" / "x.yaml",
            {
                "kind": "city",
                "name": "X",
                "position": {"x": 0, "y": 0},
                "params": {"population": 1, "vibe": 3},
            },
        )
        assert any("vibe" in e for e in errors_of(world_dir))


class TestReferences:
    def test_exit_target_must_exist(self, world_dir):
        write(
            world_dir / "nodes" / "tavern" / "attic.yaml",
            {"kind": "room", "name": "Attic", "exits": [{"to": "ghost-room"}]},
        )
        assert any("ghost-room" in e for e in errors_of(world_dir))

    def test_edge_endpoints_must_exist(self, world_dir):
        write(world_dir / "edges" / "e.yaml", {"from": "karak", "to": "nowhere", "mode": "foot"})
        assert any("nowhere" in e for e in errors_of(world_dir))

    def test_edge_mode_must_exist(self, world_dir):
        write(world_dir / "edges" / "e.yaml", {"from": "karak", "to": "tavern", "mode": "griffon"})
        assert any("griffon" in e for e in errors_of(world_dir))

    def test_edge_encounter_table_must_exist(self, world_dir):
        write(
            world_dir / "edges" / "e.yaml",
            {"from": "karak", "to": "tavern", "mode": "foot", "encounter_table": "ghosts"},
        )
        assert any("ghosts" in e for e in errors_of(world_dir))

    def test_scenario_start_location_must_exist(self, world_dir):
        write(
            world_dir / "scenario.yaml",
            {"opening": {"narration": "hi", "start_location": "atlantis"}},
        )
        assert any("atlantis" in e for e in errors_of(world_dir))

    def test_npc_location_must_exist(self, world_dir):
        write(world_dir / "npcs" / "bob.yaml", {"name": "Bob", "location": "atlantis"})
        assert any("atlantis" in e for e in errors_of(world_dir))

    def test_npc_faction_must_exist(self, world_dir):
        write(world_dir / "npcs" / "bob.yaml", {"name": "Bob", "faction": "ghost-guild"})
        assert any("ghost-guild" in e for e in errors_of(world_dir))

    def test_faction_relation_must_exist(self, world_dir):
        write(
            world_dir / "factions" / "guild.yaml",
            {"name": "Guild", "relations": {"phantoms": {"stance": -5}}},
        )
        assert any("phantoms" in e for e in errors_of(world_dir))
