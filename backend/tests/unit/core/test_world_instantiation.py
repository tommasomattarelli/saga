"""ADR 0008 S2 — World asset → world_baseline + initial world_state (A6/D7/C11)."""

import uuid
from pathlib import Path

from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world
from app.memory.world_state import CURRENT_SCHEMA_VERSION

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


def npc_named(state: dict, name: str) -> dict:
    return next(n for n in state["npcs"].values() if n["name"] == name)


class TestOverlay:
    def test_schema_v7_and_start_position(self):
        baseline, state, _ = instantiated()
        start_id = baseline["slug_map"]["shrine-of-first-light"]
        assert state["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION
        assert state["player_position"] == start_id
        assert state["meta"]["current_location"] == start_id

    def test_npcs_keyed_by_uuid_with_slug_alias(self):
        # ADR 0009 F1 — runtime UUIDs; slug + name become resolution aliases.
        _, state, _ = instantiated()
        for key, npc in state["npcs"].items():
            assert is_uuid(key)
            assert npc["name"]
        assert npc_named(state, "Lyra")["slug"] == "lyra"

    def test_npcs_seeded_with_uuid_locations(self):
        baseline, state, _ = instantiated()
        marta = npc_named(state, "Marta")
        assert marta["location"] == baseline["slug_map"]["thornhaven"]
        assert marta["last_interactions"] == []
        assert marta["lifecycle"] == "alive"
        assert marta["condition"] is None

    def test_npc_traits_seeded_from_defaults_and_authored(self):
        # ADR 0009 G1 — taxonomy defaults ⊕ authored flat descriptives.
        _, state, _ = instantiated()
        lyra = npc_named(state, "Lyra")
        assert lyra["traits"]["role"] == "Forest ranger"  # authored
        assert lyra["traits"]["ideal"] == ""  # taxonomy default
        assert "role" not in lyra  # descriptives live only in traits

    def test_npc_psychology_seeded_at_defaults(self):
        _, state, _ = instantiated()
        marta = npc_named(state, "Marta")
        assert marta["psychology"] == {"trust": 0, "respect": 0, "affection": 0, "fear": 0}
        assert marta["met_player"] is False
        assert "disposition_toward_player" not in marta

    def test_authored_psychology_merged_over_defaults(self):
        _, state, _ = instantiated()
        lyra = npc_named(state, "Lyra")
        assert lyra["psychology"]["trust"] == -20  # authored in lyra.yaml
        assert lyra["psychology"]["respect"] == 0
        assert lyra["met_player"] is False  # authored seed never flips it (B3)

    def test_runtime_containers_seeded(self):
        _, state, _ = instantiated()
        assert state["node_status"] == {}
        assert state["edge_overrides"] == []
        assert state["consumed_encounters"] == {}
        assert "combat_state" not in state  # combat is not a mode (ADR 0003 B1)
        assert state["clock"]["total_minutes"] == 480

    def test_seeded_clock_carries_the_derived_fields(self):
        """advance_game_clock dumps the computed fields; the seed must match it from turn 1."""
        _, state, _ = instantiated()
        assert state["clock"]["current_day"] == 1
        assert state["clock"]["time_of_day"] == "morning"

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
