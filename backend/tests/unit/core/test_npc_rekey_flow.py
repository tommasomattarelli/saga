"""ADR 0009 S1 — regression: no ghost name-keyed records after the uuid rekey.

Advisor findings 1-2: every read/write must resolve names to uuid keys; a
dialogue turn on a rekeyed save must mint zero new npc keys, and the scene
must render names, not uuids.
"""

from app.ai.router import GameplayConfig
from app.core.dm.npc_prehook import validate_or_create_npc
from app.core.npc_resolver import npcs_at_current_location
from app.memory.updater import apply_typed_updates

LYRA_ID = "11111111-1111-1111-1111-111111111111"


def rekeyed_state() -> dict:
    return {
        "meta": {"schema_version": 7, "current_location": "node-1"},
        "npcs": {
            LYRA_ID: {
                "slug": "lyra",
                "name": "Lyra",
                "lifecycle": "alive",
                "condition": None,
                "location": "node-1",
                "faction": None,
                "psychology": {"trust": -20},
                "met_player": False,
                "last_interactions": [],
                "traits": {"role": "Forest ranger"},
            }
        },
    }


def config(**overrides) -> GameplayConfig:
    return GameplayConfig(**overrides)


class TestPrehookOnRekeyedSave:
    def test_known_npc_resolves_without_minting_a_key(self):
        state = rekeyed_state()
        ok, error = validate_or_create_npc("Lyra", state, config())
        assert ok and error == ""
        assert set(state["npcs"]) == {LYRA_ID}

    def test_dead_npc_gated_by_lifecycle_only(self):
        state = rekeyed_state()
        state["npcs"][LYRA_ID]["lifecycle"] = "dead"
        ok, error = validate_or_create_npc("Lyra", state, config())
        assert not ok
        assert "dead" in error

    def test_auto_create_mints_uuid_key(self):
        state = rekeyed_state()
        ok, _ = validate_or_create_npc("Stranger", state, config())
        assert ok
        new_keys = set(state["npcs"]) - {LYRA_ID}
        assert len(new_keys) == 1
        new_npc = state["npcs"][new_keys.pop()]
        assert new_npc["name"] == "Stranger"
        assert new_npc["lifecycle"] == "alive"


class TestPsychologyUpdateOnRekeyedSave:
    def test_name_target_resolves_to_existing_record(self):
        state = rekeyed_state()
        update = {"key": "npc_psychology", "target": "Lyra", "changes": {"trust": 5}}
        new_state, _ = apply_typed_updates(state, {}, [update])
        assert set(new_state["npcs"]) == {LYRA_ID}  # no ghost record
        lyra = new_state["npcs"][LYRA_ID]
        assert lyra["met_player"] is True
        assert lyra["psychology"]["trust"] == -5  # -20 + 5×3 first impression

    def test_uuid_target_hits_directly(self):
        state = rekeyed_state()
        update = {"key": "npc_psychology", "target": LYRA_ID, "changes": {"trust": 5}}
        new_state, _ = apply_typed_updates(state, {}, [update])
        assert set(new_state["npcs"]) == {LYRA_ID}


class TestSceneOnRekeyedSave:
    def test_scene_lookup_keeps_uuid_keys_and_names(self):
        present = npcs_at_current_location(rekeyed_state())
        assert set(present) == {LYRA_ID}
        assert present[LYRA_ID]["name"] == "Lyra"

    def test_dead_and_removed_filtered_from_scene(self):
        state = rekeyed_state()
        state["npcs"][LYRA_ID]["lifecycle"] = "removed"
        assert npcs_at_current_location(state) == {}
