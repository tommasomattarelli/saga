"""Statblocks on the NPC record, at birth and through the v7→v8 rung (ADR 0003 B2/B3/F)."""

from app.core.npc_classes import DEFAULT_NPC_CLASSES, statblock_defaults
from app.core.npc_scaffold import create_npc_record
from app.memory.world_state import CURRENT_SCHEMA_VERSION, migrate_world_state
from app.models.npc import IMMUTABLE_FIELDS, MUTABLE_FIELDS, NpcEngineRecord

STATBLOCK_FIELDS = {"hp", "max_hp", "defense", "attack_mod", "damage_class", "npc_class"}


class TestPartition:
    def test_every_field_sits_in_exactly_one_set(self):
        assert set(NpcEngineRecord.model_fields) == MUTABLE_FIELDS | IMMUTABLE_FIELDS
        assert not MUTABLE_FIELDS & IMMUTABLE_FIELDS

    def test_update_npc_can_never_write_a_statblock_number(self):
        """MUTABLE_FIELDS is what the LLM's update_npc may write — HP must stay out."""
        assert not STATBLOCK_FIELDS & MUTABLE_FIELDS
        assert STATBLOCK_FIELDS <= IMMUTABLE_FIELDS

    def test_auto_created_is_set_at_birth_and_never_edited(self):
        assert "auto_created" in IMMUTABLE_FIELDS


class TestCreationScaffold:
    def test_a_new_record_carries_a_full_statblock(self):
        npc = create_npc_record("Goblin", npc_classes=DEFAULT_NPC_CLASSES)
        assert set(npc) >= STATBLOCK_FIELDS
        assert all(npc[field] is not None for field in STATBLOCK_FIELDS)

    def test_hp_starts_full_and_inside_the_class_range(self):
        npc = create_npc_record("Goblin", npc_class="commoner", npc_classes=DEFAULT_NPC_CLASSES)
        assert npc["hp"] == npc["max_hp"]
        assert 5 <= npc["max_hp"] <= 10

    def test_the_class_decides_the_numbers(self):
        commander = create_npc_record(
            "Vex", npc_class="commander", npc_classes=DEFAULT_NPC_CLASSES
        )
        assert commander["npc_class"] == "commander"
        assert commander["max_hp"] >= 35

    def test_an_absent_class_falls_to_the_configured_default(self):
        npc = create_npc_record("Nobody", npc_classes=DEFAULT_NPC_CLASSES)
        assert npc["npc_class"] == statblock_defaults()["npc_class"]

    def test_the_scaffold_plants_the_npc_at_the_current_node(self):
        """The 0009 scaffold left location None; presence guards and the death
        writer both rely on it (ADR 0003 B3b, fix folded in)."""
        npc = create_npc_record("Goblin", location="node-uuid-7")
        assert npc["location"] == "node-uuid-7"

    def test_auto_created_marks_only_records_the_engine_invented(self):
        assert create_npc_record("Goblin", auto_created=True)["auto_created"] is True
        assert create_npc_record("Mirella")["auto_created"] is False


class TestRungV8:
    def _v7_state(self) -> dict:
        return {
            "meta": {"schema_version": 7},
            "npcs": {
                "uuid-1": {
                    "name": "Mirella",
                    "lifecycle": "alive",
                    "psychology": {"trust": 0},
                    "traits": {"role": "innkeeper"},
                }
            },
        }

    def test_the_rung_backfills_a_statblock_on_every_record(self):
        state = migrate_world_state(self._v7_state())
        npc = state["npcs"]["uuid-1"]
        assert set(npc) >= STATBLOCK_FIELDS
        assert npc["hp"] == npc["max_hp"] > 0

    def test_backfilled_records_are_not_marked_auto_created(self):
        """They predate the mook hook, so the prune must never touch them (B2)."""
        state = migrate_world_state(self._v7_state())
        assert state["npcs"]["uuid-1"]["auto_created"] is False

    def test_the_rung_drops_the_combat_state(self):
        state = migrate_world_state({**self._v7_state(), "combat_state": {"active": True}})
        assert "combat_state" not in state

    def test_it_leaves_the_state_at_the_current_version(self):
        state = migrate_world_state(self._v7_state())
        assert state["meta"]["schema_version"] == CURRENT_SCHEMA_VERSION == 8

    def test_migrating_twice_changes_nothing(self):
        once = migrate_world_state(self._v7_state())
        assert migrate_world_state(once) == once
