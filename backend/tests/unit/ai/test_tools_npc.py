"""ADR 0009 S2 — update_npc: upsert, B2 partition enforcement, B4 fuzzy guard."""

from app.ai.tools.dm_tools import execute_tool

LYRA_ID = "11111111-1111-1111-1111-111111111111"
G1_ID = "22222222-2222-2222-2222-222222222222"
G2_ID = "33333333-3333-3333-3333-333333333333"


def state_with_lyra() -> dict:
    return {
        "meta": {"current_location": "node-1"},
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


def run(args: dict, state: dict | None = None, baseline: dict | None = None):
    state = state if state is not None else state_with_lyra()
    result = execute_tool("update_npc", args, state, {}, baseline=baseline)
    return result, result.world_state


class TestUpdateExisting:
    def test_updates_engine_field_and_trait_in_place(self):
        result, ws = run({"name": "Lyra", "updates": {"condition": "wounded", "role": "Fugitive"}})
        assert set(ws["npcs"]) == {LYRA_ID}
        lyra = ws["npcs"][LYRA_ID]
        assert lyra["condition"] == "wounded"
        assert lyra["traits"]["role"] == "Fugitive"
        assert "Lyra" in result.description

    def test_rename_is_a_reveal_same_record(self):
        _, ws = run({"name": "Lyra", "updates": {"name": "Lyra of the Vale"}})
        lyra = ws["npcs"][LYRA_ID]
        assert lyra["name"] == "Lyra of the Vale"
        assert lyra["psychology"] == {"trust": -20}  # history/psychology intact

    def test_immutable_field_rejected_with_writable_list(self):
        result, ws = run({"name": "Lyra", "updates": {"lifecycle": "dead"}})
        assert ws["npcs"][LYRA_ID]["lifecycle"] == "alive"
        assert "lifecycle" in result.description
        assert "condition" in result.description  # writable fields listed

    def test_psychology_rejected(self):
        result, ws = run({"name": "Lyra", "updates": {"psychology": "happy"}})
        assert ws["npcs"][LYRA_ID]["psychology"] == {"trust": -20}
        assert "not writable" in result.description

    def test_undeclared_trait_rejected_with_declared(self):
        result, _ = run({"name": "Lyra", "updates": {"honor_code": "strict"}})
        assert "honor_code" in result.description
        assert "role" in result.description  # declared npc_fields listed


class TestFuzzyGuard:
    def test_typo_near_hit_rejects_without_creating(self):
        result, ws = run({"name": "Lyrra", "updates": {"condition": "angry"}})
        assert set(ws["npcs"]) == {LYRA_ID}  # no duplicate minted
        assert "Lyra" in result.description
        assert "create" in result.description  # points at the escape hatch

    def test_create_true_forces_new_npc_despite_near_name(self):
        _, ws = run({"name": "Lyrra", "updates": {"role": "Impostor"}, "create": True})
        new_ids = set(ws["npcs"]) - {LYRA_ID}
        assert len(new_ids) == 1
        impostor = ws["npcs"][new_ids.pop()]
        assert impostor["name"] == "Lyrra"
        assert impostor["traits"]["role"] == "Impostor"
        assert impostor["lifecycle"] == "alive"

    def test_clean_new_name_creates_directly(self):
        _, ws = run({"name": "Grumbold", "updates": {"role": "Blacksmith"}})
        grumbold = next(n for n in ws["npcs"].values() if n["name"] == "Grumbold")
        assert grumbold["traits"]["role"] == "Blacksmith"
        assert grumbold["traits"]["personality"] == ""  # scaffold defaults present


class TestAmbiguity:
    def test_homonyms_reject_with_candidates(self):
        state = {
            "npcs": {
                G1_ID: {"name": "Guard", "lifecycle": "alive", "traits": {}},
                G2_ID: {"name": "Guard", "lifecycle": "alive", "traits": {}},
            }
        }
        result, ws = run({"name": "Guard", "updates": {"condition": "alert"}}, state=state)
        assert ws["npcs"][G1_ID].get("condition") is None
        assert "Guard" in result.description
        assert "specify" in result.description.lower()


class TestConditionCap:
    def test_condition_over_cap_rejected(self):
        # A4/std 14: cap from saga.config.yaml (default 80 chars).
        long_condition = "wounded and " + "very " * 30 + "angry"
        result, ws = run({"name": "Lyra", "updates": {"condition": long_condition}})
        assert ws["npcs"][LYRA_ID]["condition"] is None
        assert "too long" in result.description

    def test_condition_within_cap_accepted(self):
        _, ws = run({"name": "Lyra", "updates": {"condition": "wounded, wary"}})
        assert ws["npcs"][LYRA_ID]["condition"] == "wounded, wary"


class TestKillNpc:
    def test_kill_present_npc(self):
        result = execute_tool("kill_npc", {"name": "Lyra", "cause": "duel"}, state_with_lyra(), {})
        lyra = result.world_state["npcs"][LYRA_ID]
        assert lyra["lifecycle"] == "dead"
        assert "duel" in result.description

    def test_kill_npc_elsewhere_rejected(self):
        state = state_with_lyra()
        state["npcs"][LYRA_ID]["location"] = "node-2"
        result = execute_tool("kill_npc", {"name": "Lyra", "cause": "duel"}, state, {})
        assert result.world_state["npcs"][LYRA_ID]["lifecycle"] == "alive"
        assert "elsewhere" in result.description

    def test_kill_dead_npc_rejected(self):
        state = state_with_lyra()
        state["npcs"][LYRA_ID]["lifecycle"] = "dead"
        result = execute_tool("kill_npc", {"name": "Lyra", "cause": "again"}, state, {})
        assert "dead" in result.description

    def test_kill_ambiguous_rejected(self):
        state = {
            "meta": {"current_location": "node-1"},
            "npcs": {
                G1_ID: {"name": "Guard", "lifecycle": "alive", "location": "node-1"},
                G2_ID: {"name": "Guard", "lifecycle": "alive", "location": "node-1"},
            },
        }
        result = execute_tool("kill_npc", {"name": "Guard", "cause": "duel"}, state, {})
        assert all(n["lifecycle"] == "alive" for n in result.world_state["npcs"].values())
        assert "Multiple" in result.description

    def test_lifecycle_not_writable_via_update_npc(self):
        # A3: the generic field write can never flip life state.
        result, ws = run({"name": "Lyra", "updates": {"lifecycle": "dead"}})
        assert ws["npcs"][LYRA_ID]["lifecycle"] == "alive"


class TestRemoveRestore:
    def test_remove_then_restore_roundtrip(self):
        state = state_with_lyra()
        result = execute_tool("remove_npc", {"name": "Lyra", "reason": "left town"}, state, {})
        assert result.world_state["npcs"][LYRA_ID]["lifecycle"] == "removed"
        assert "left town" in result.description

        result = execute_tool("restore_npc", {"name": "Lyra"}, result.world_state, {})
        assert result.world_state["npcs"][LYRA_ID]["lifecycle"] == "alive"

    def test_restore_dead_rejected_terminal(self):
        state = state_with_lyra()
        state["npcs"][LYRA_ID]["lifecycle"] = "dead"
        result = execute_tool("restore_npc", {"name": "Lyra"}, state, {})
        assert result.world_state["npcs"][LYRA_ID]["lifecycle"] == "dead"
        assert "final" in result.description

    def test_restore_alive_rejected(self):
        result = execute_tool("restore_npc", {"name": "Lyra"}, state_with_lyra(), {})
        assert "already present" in result.description

    def test_restore_with_location_resolves_place(self):
        baseline = {
            "nodes": {"node-2": {"name": "Thornhaven", "parent": None}},
            "alias": {"thornhaven": ["node-2"]},
        }
        state = state_with_lyra()
        state["npcs"][LYRA_ID]["lifecycle"] = "removed"
        result = execute_tool(
            "restore_npc", {"name": "Lyra", "location": "Thornhaven"}, state, {}, baseline=baseline
        )
        lyra = result.world_state["npcs"][LYRA_ID]
        assert lyra["lifecycle"] == "alive"
        assert lyra["location"] == "node-2"


class TestLocationResolution:
    def test_location_resolved_to_node_uuid_via_baseline(self):
        baseline = {
            "nodes": {
                "node-1": {"name": "Shrine", "parent": None},
                "node-2": {"name": "Thornhaven", "parent": None},
            },
            "alias": {"thornhaven": ["node-2"], "shrine": ["node-1"]},
            "slug_map": {},
        }
        _, ws = run({"name": "Lyra", "updates": {"location": "Thornhaven"}}, baseline=baseline)
        assert ws["npcs"][LYRA_ID]["location"] == "node-2"

    def test_unknown_place_rejected(self):
        baseline = {"nodes": {"node-1": {"name": "Shrine", "parent": None}}, "alias": {}}
        result, ws = run({"name": "Lyra", "updates": {"location": "Atlantis"}}, baseline=baseline)
        assert ws["npcs"][LYRA_ID]["location"] == "node-1"
        assert "Atlantis" in result.description
