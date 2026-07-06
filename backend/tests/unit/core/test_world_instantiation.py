"""ADR 0008 S2 — World asset → world_baseline + initial world_state (A6/D7/C11)."""

import uuid
from pathlib import Path

from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world

EXAMPLE_WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def instantiated():
    return instantiate_world(load_world(EXAMPLE_WORLD))


class TestBaseline:
    def test_every_node_gets_a_uuid(self):
        baseline, _, _ = instantiated()
        assert all(is_uuid(k) for k in baseline["nodes"])
        assert len(baseline["nodes"]) == len(baseline["slug_map"])

    def test_slug_map_roundtrip(self):
        baseline, _, _ = instantiated()
        for slug, node_id in baseline["slug_map"].items():
            assert baseline["nodes"][node_id]["slug"] == slug

    def test_parent_children_are_uuids(self):
        baseline, _, _ = instantiated()
        root_id = baseline["root"]
        assert baseline["nodes"][root_id]["parent"] is None
        for node_id, node in baseline["nodes"].items():
            if node["parent"] is not None:
                assert node_id in baseline["nodes"][node["parent"]]["children"]

    def test_scale_denormalized_on_nodes(self):
        baseline, _, _ = instantiated()
        tavern = baseline["nodes"][baseline["slug_map"]["gilded-tankard"]]
        assert tavern["scale"] == "interior"

    def test_global_km_composed(self):
        baseline, _, _ = instantiated()
        # world km_per_unit=5, region at (10,8) → (50,40); region km_per_unit=1,
        # shrine at (2,3) → (52,43)
        shrine = baseline["nodes"][baseline["slug_map"]["shrine-of-first-light"]]
        assert shrine["global_km"] == {"x": 52.0, "y": 43.0}

    def test_interior_nodes_have_no_global_km(self):
        baseline, _, _ = instantiated()
        tavern = baseline["nodes"][baseline["slug_map"]["gilded-tankard"]]
        assert tavern["global_km"] is None

    def test_edges_reference_uuids(self):
        baseline, _, _ = instantiated()
        edge = baseline["edges"]["forest-path"]
        assert edge["from"] in baseline["nodes"]
        assert edge["to"] in baseline["nodes"]

    def test_alias_index_maps_names_and_slugs(self):
        baseline, _, _ = instantiated()
        shrine_id = baseline["slug_map"]["shrine-of-first-light"]
        assert shrine_id in baseline["alias"]["shrine of first light"]
        assert shrine_id in baseline["alias"]["shrine-of-first-light"]

    def test_taxonomy_and_collections_frozen_in(self):
        baseline, _, _ = instantiated()
        assert any(k["name"] == "site" for k in baseline["taxonomy"]["kinds"])
        assert "thornhaven-council" in baseline["factions"]
        assert "north-road-encounters" in baseline["encounters"]
        assert baseline["source_world"] == "the-awakening"
        assert baseline["world_version"] == "1.0.0"


class TestOverlay:
    def test_schema_v5_and_start_position(self):
        baseline, state, _ = instantiated()
        start_id = baseline["slug_map"]["shrine-of-first-light"]
        assert state["meta"]["schema_version"] == 5
        assert state["player_position"] == start_id
        assert state["meta"]["current_location"] == start_id

    def test_npcs_seeded_with_uuid_locations(self):
        baseline, state, _ = instantiated()
        marta = state["npcs"]["Marta"]
        assert marta["location"] == baseline["slug_map"]["thornhaven"]
        assert marta["disposition_toward_player"] == 0
        assert marta["last_interactions"] == []

    def test_runtime_containers_seeded(self):
        _, state, _ = instantiated()
        assert state["node_status"] == {}
        assert state["edge_overrides"] == []
        assert state["consumed_encounters"] == {}
        assert state["combat_state"]["active"] is False
        assert state["clock"]["total_minutes"] == 480

    def test_opening_seeds_time_weather_and_narration(self):
        _, state, _ = instantiated()
        assert state["time_of_day"] == "morning"
        assert state["weather"] == "clear"
        assert "canopy of ancient oaks" in state["meta"]["opening_narration"]

    def test_factions_seeded_by_name(self):
        _, state, _ = instantiated()
        assert state["factions"]["The Hollow"]["disposition"] == 0


class TestQuests:
    def test_initial_quests_shape(self):
        _, _, quests = instantiated()
        assert quests["active"][0]["name"] == "Who Am I?"
        assert quests["active"][0]["objectives"]
