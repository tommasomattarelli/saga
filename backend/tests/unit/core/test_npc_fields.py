"""ADR 0009 S1 — world-defined NPC descriptive fields (G1/G2/G4)."""

import pytest
from pydantic import ValidationError

from app.core.npc_fields import DEFAULT_NPC_FIELDS, default_traits, resolve_npc_fields
from app.models.npc_fields import NpcFieldDef
from app.models.world import NpcRecord, Taxonomy

MINIMAL_TAXONOMY = {"kinds": [{"name": "region", "scale": "outdoor"}]}


class TestNpcFieldDef:
    def test_minimal(self):
        f = NpcFieldDef(name="role")
        assert f.default == ""
        assert f.scene is False

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError):
            NpcFieldDef(name="role", audience="dm")


class TestBundledDefault:
    def test_field_names(self):
        names = [f.name for f in DEFAULT_NPC_FIELDS]
        assert names == [
            "role",
            "appearance",
            "personality",
            "motivation",
            "background",
            "ideal",
            "bond",
            "flaw",
            "mannerisms",
            "secret",
            "dreads",
        ]

    def test_fear_is_not_a_field_name(self):
        # G2: `fear` is a psychology axis; the trait is `dreads`.
        assert "fear" not in {f.name for f in DEFAULT_NPC_FIELDS}

    def test_scene_routing(self):
        # G3: the DM narrates what the player perceives; the rest is interiority.
        scene_fields = {f.name for f in DEFAULT_NPC_FIELDS if f.scene}
        assert scene_fields == {"role", "appearance"}

    def test_default_traits_shape(self):
        traits = default_traits(DEFAULT_NPC_FIELDS)
        assert traits["role"] == "Commoner"
        assert set(traits) == {f.name for f in DEFAULT_NPC_FIELDS}


class TestResolveNpcFields:
    def test_none_taxonomy_falls_back(self):
        assert resolve_npc_fields(None) == DEFAULT_NPC_FIELDS

    def test_taxonomy_without_block_falls_back(self):
        assert resolve_npc_fields(MINIMAL_TAXONOMY) == DEFAULT_NPC_FIELDS

    def test_world_block_wins(self):
        taxonomy = {
            **MINIMAL_TAXONOMY,
            "npc_fields": [{"name": "honor_code", "default": "none", "scene": True}],
        }
        fields = resolve_npc_fields(taxonomy)
        assert [f.name for f in fields] == ["honor_code"]
        assert fields[0].scene is True


class TestTaxonomyBlock:
    def test_accepts_npc_fields(self):
        t = Taxonomy(
            **MINIMAL_TAXONOMY,
            npc_fields=[{"name": "role"}, {"name": "honor_code", "scene": True}],
        )
        assert t.npc_field("honor_code").scene is True
        assert t.npc_field("missing") is None

    def test_default_is_none(self):
        assert Taxonomy(**MINIMAL_TAXONOMY).npc_fields is None

    def test_duplicate_names_rejected(self):
        with pytest.raises(ValidationError, match="duplicate npc_field"):
            Taxonomy(**MINIMAL_TAXONOMY, npc_fields=[{"name": "role"}, {"name": "role"}])


class TestNpcRecordDescriptives:
    def test_descriptives_collects_extras(self):
        npc = NpcRecord(slug="lyra", name="Lyra", role="Ranger", honor_code="strict")
        assert npc.descriptives() == {"role": "Ranger", "honor_code": "strict"}

    def test_engine_fields_not_in_descriptives(self):
        npc = NpcRecord(slug="lyra", name="Lyra", psychology={"trust": -20})
        assert npc.descriptives() == {}
