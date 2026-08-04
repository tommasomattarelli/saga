"""World-defined NPC classes and their statblock templates (ADR 0003 B3b)."""

import pytest
from pydantic import ValidationError

from app.core.npc_classes import (
    DEFAULT_NPC_CLASSES,
    draw_statblock,
    resolve_npc_classes,
    statblock_defaults,
)
from app.models.npc_class import NpcClassDef

_CUSTOM = {
    "npc_classes": [
        {"name": "peon", "hp_class": "weak", "defense": "trivial", "damage_class": "unarmed"},
        {"name": "warlord", "hp_class": "boss", "defense": "very_hard", "attack_mod": 7},
    ]
}


class TestResolution:
    def test_a_world_without_the_block_gets_the_bundled_default(self):
        assert resolve_npc_classes(None) == DEFAULT_NPC_CLASSES
        assert resolve_npc_classes({}) == DEFAULT_NPC_CLASSES

    def test_a_world_may_define_its_own_archetypes(self):
        classes = resolve_npc_classes(_CUSTOM)
        assert [c.name for c in classes] == ["peon", "warlord"]
        assert classes[1].hp_class == "boss"

    def test_the_bundled_default_covers_the_statblock_defaults_class(self):
        """statblock_defaults names a class; it must exist or the fallback dead-ends."""
        assert any(c.name == statblock_defaults()["npc_class"] for c in DEFAULT_NPC_CLASSES)


class TestClassDefinition:
    def test_unknown_hp_class_is_rejected(self):
        with pytest.raises(ValidationError):
            NpcClassDef(name="x", hp_class="colossal")

    def test_defense_reuses_the_difficulty_levels(self):
        with pytest.raises(ValidationError):
            NpcClassDef(name="x", defense="impossible")
        assert NpcClassDef(name="x", defense="near_impossible").defense == "near_impossible"

    def test_attack_mod_is_clamped_by_config(self):
        assert NpcClassDef(name="x", attack_mod=99).attack_mod == 10
        assert NpcClassDef(name="x", attack_mod=-99).attack_mod == -2


class TestStatblockDraw:
    """The LLM emits classes; every number is drawn here (B3b)."""

    def test_hp_is_drawn_from_the_class_range(self):
        rolls = {draw_statblock("commoner", DEFAULT_NPC_CLASSES)["max_hp"] for _ in range(200)}
        assert min(rolls) >= 5
        assert max(rolls) <= 10

    def test_hp_starts_full(self):
        block = draw_statblock("guard", DEFAULT_NPC_CLASSES)
        assert block["hp"] == block["max_hp"]

    def test_the_class_template_carries_the_mechanics(self):
        block = draw_statblock("commander", DEFAULT_NPC_CLASSES)
        assert block["npc_class"] == "commander"
        assert block["damage_class"] == "heavy"
        assert block["attack_mod"] > 0

    def test_a_butcher_can_never_have_general_grade_numbers(self):
        """The free-text role trait stays descriptive; the class carries the numbers."""
        commoner = draw_statblock("commoner", DEFAULT_NPC_CLASSES)
        commander = draw_statblock("commander", DEFAULT_NPC_CLASSES)
        assert commoner["max_hp"] < commander["max_hp"]
        assert commoner["attack_mod"] < commander["attack_mod"]

    def test_an_unknown_class_falls_back_to_the_default_class_template(self):
        """B3b's two steps: the class template first, statblock_defaults only after."""
        fallback = statblock_defaults()["npc_class"]
        template = next(c for c in DEFAULT_NPC_CLASSES if c.name == fallback)
        block = draw_statblock("necromancer-king", DEFAULT_NPC_CLASSES)
        assert block["npc_class"] == fallback
        assert block["damage_class"] == template.damage_class.value

    def test_statblock_defaults_bite_only_when_the_world_declares_no_classes(self):
        defaults = statblock_defaults()
        block = draw_statblock("anything", [])
        assert block["npc_class"] == defaults["npc_class"]
        assert block["defense"] == defaults["defense"]
        assert block["damage_class"] == defaults["damage_class"]
        assert block["attack_mod"] == defaults["attack_mod"]

    def test_authored_values_win_over_the_class_template(self):
        block = draw_statblock("commoner", DEFAULT_NPC_CLASSES, authored={"attack_mod": 4})
        assert block["attack_mod"] == 4
        assert block["npc_class"] == "commoner"

    def test_an_authored_hp_is_taken_verbatim_not_redrawn(self):
        block = draw_statblock("commoner", DEFAULT_NPC_CLASSES, authored={"max_hp": 200})
        assert block["max_hp"] == 200
        assert block["hp"] == 200

    def test_every_field_is_populated_so_readers_never_meet_none(self):
        block = draw_statblock("guard", DEFAULT_NPC_CLASSES)
        assert set(block) == {"hp", "max_hp", "defense", "attack_mod", "damage_class", "npc_class"}
        assert None not in block.values()
