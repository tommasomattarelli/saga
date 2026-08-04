"""Authored statblocks ride the world loader and its tier-3 validation (ADR 0003 B3/F)."""

from pathlib import Path

import pytest

from app.core.world_instantiation import instantiate_world
from app.core.world_loader import load_world
from app.core.world_validator import validate_world
from app.models.world import NpcRecord

WORLD = Path(__file__).parents[4] / "worlds" / "the-awakening"


@pytest.fixture(scope="module")
def asset():
    return load_world(WORLD)


class TestAuthoring:
    def test_a_world_npc_may_declare_its_class(self, asset):
        assert asset.npcs["aldric"].npc_class == "royale"

    def test_the_class_is_not_mistaken_for_a_descriptive_trait(self, asset):
        """`extra=allow` collects unknown keys as traits — statblock keys must not land there."""
        assert "npc_class" not in asset.npcs["aldric"].descriptives()

    def test_an_npc_without_a_statblock_stays_silent_about_it(self, asset):
        assert asset.npcs["marta"].npc_class is None
        assert asset.npcs["marta"].statblock() == {}

    def test_only_authored_overrides_are_reported(self):
        npc = NpcRecord(slug="vex", name="Vex", npc_class="commander", attack_mod=6)
        assert npc.statblock() == {"attack_mod": 6}


class TestTierThreeValidation:
    def test_the_reference_world_validates(self, asset):
        assert validate_world(asset, max_depth=8) == []

    def test_an_undeclared_class_is_rejected_with_the_declared_ones(self, asset):
        asset.npcs["aldric"].npc_class = "lich-emperor"
        try:
            errors = validate_world(asset, max_depth=8)
        finally:
            asset.npcs["aldric"].npc_class = "royale"
        assert any("unknown npc class 'lich-emperor'" in e for e in errors)
        assert any("commander" in e for e in errors)


class TestInstantiation:
    def test_the_authored_class_reaches_the_runtime_record(self, asset):
        _, state, _ = instantiate_world(asset)
        aldric = next(n for n in state["npcs"].values() if n["slug"] == "aldric")
        assert aldric["npc_class"] == "royale"
        assert 5 <= aldric["max_hp"] <= 10  # royale → hp_class weak

    def test_an_unauthored_npc_still_gets_a_full_statblock(self, asset):
        _, state, _ = instantiate_world(asset)
        marta = next(n for n in state["npcs"].values() if n["slug"] == "marta")
        assert marta["npc_class"] is not None
        assert marta["hp"] == marta["max_hp"] > 0

    def test_authored_npcs_are_never_marked_auto_created(self, asset):
        """Only what the engine invented is ever prunable (B2)."""
        _, state, _ = instantiate_world(asset)
        assert all(npc["auto_created"] is False for npc in state["npcs"].values())
