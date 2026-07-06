"""ADR 0008 S1 — meta-schema (taxonomy) + base node models."""

import pytest
from pydantic import ValidationError

from app.models.world import (
    EncounterTable,
    FactionDef,
    KindDef,
    Taxonomy,
    WorldNode,
)


def make_taxonomy(**overrides) -> Taxonomy:
    data = {
        "kinds": [
            {"name": "region", "scale": "outdoor"},
            {"name": "room", "scale": "interior"},
        ],
        "terrains": [{"name": "road", "travel_multiplier": 0.75}],
        "travel_modes": [{"name": "foot", "speed_kmh": 4}],
    }
    data.update(overrides)
    return Taxonomy(**data)


class TestTaxonomy:
    def test_minimal_taxonomy_valid(self):
        tax = Taxonomy(kinds=[{"name": "place", "scale": "outdoor"}])
        assert tax.kind("place").scale == "outdoor"

    def test_at_least_one_kind_required(self):
        with pytest.raises(ValidationError):
            Taxonomy(kinds=[])

    def test_duplicate_kind_names_rejected(self):
        with pytest.raises(ValidationError):
            make_taxonomy(
                kinds=[
                    {"name": "region", "scale": "outdoor"},
                    {"name": "region", "scale": "interior"},
                ]
            )

    def test_duplicate_terrain_names_rejected(self):
        with pytest.raises(ValidationError):
            make_taxonomy(
                terrains=[
                    {"name": "road", "travel_multiplier": 0.75},
                    {"name": "road", "travel_multiplier": 2.0},
                ]
            )

    def test_travel_multiplier_must_be_positive(self):
        with pytest.raises(ValidationError):
            make_taxonomy(terrains=[{"name": "void", "travel_multiplier": 0}])

    def test_mode_speed_must_be_positive(self):
        with pytest.raises(ValidationError):
            make_taxonomy(travel_modes=[{"name": "still", "speed_kmh": 0}])

    def test_default_terrain_must_exist(self):
        with pytest.raises(ValidationError):
            make_taxonomy(defaults={"terrain": "lava"})

    def test_lookup_helpers(self):
        tax = make_taxonomy()
        assert tax.terrain("road").travel_multiplier == 0.75
        assert tax.mode("foot").speed_kmh == 4
        assert tax.kind("missing") is None

    def test_param_defs_validate(self):
        tax = make_taxonomy(
            kinds=[
                {
                    "name": "city",
                    "scale": "outdoor",
                    "params": [{"name": "population", "type": "int", "required": True, "min": 0}],
                }
            ]
        )
        assert tax.kind("city").params[0].required is True


class TestKindDef:
    def test_scale_must_be_outdoor_or_interior(self):
        with pytest.raises(ValidationError):
            KindDef(name="x", scale="underwater")

    def test_duplicate_param_names_rejected(self):
        with pytest.raises(ValidationError):
            KindDef(
                name="x",
                scale="outdoor",
                params=[{"name": "a"}, {"name": "a"}],
            )


class TestWorldNode:
    def test_minimal_node(self):
        node = WorldNode(slug="karak", kind="city", name="Karak")
        assert node.km_per_unit == 1.0
        assert node.params == {}

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            WorldNode(slug="karak", kind="city", name="Karak", dragons=7)

    def test_slug_must_be_kebab_case(self):
        with pytest.raises(ValidationError):
            WorldNode(slug="Karak City", kind="city", name="Karak")

    def test_item_qty_must_be_positive(self):
        with pytest.raises(ValidationError):
            WorldNode(
                slug="karak",
                kind="city",
                name="Karak",
                items=[{"name": "gold", "qty": 0}],
            )

    def test_exits_parse(self):
        node = WorldNode(
            slug="hall",
            kind="room",
            name="Hall",
            exits=[{"to": "kitchen"}, {"to": "cellar", "locked": True}],
        )
        assert node.exits[1].locked is True


class TestEncounterTable:
    def test_valid_table(self):
        table = EncounterTable(
            slug="north-road",
            dice="2d8",
            entries=[
                {"roll": [2, 4], "type": "combat", "description": "Bandits"},
                {"roll": [5, 16], "type": "event", "description": "Merchant", "once": True},
            ],
        )
        assert table.entries[1].once is True

    def test_bad_dice_notation_rejected(self):
        with pytest.raises(ValidationError):
            EncounterTable(
                slug="x",
                dice="banana",
                entries=[{"roll": [1, 2], "type": "event", "description": "y"}],
            )

    def test_roll_range_min_le_max(self):
        with pytest.raises(ValidationError):
            EncounterTable(
                slug="x",
                dice="1d6",
                entries=[{"roll": [5, 2], "type": "event", "description": "y"}],
            )

    def test_at_least_one_entry(self):
        with pytest.raises(ValidationError):
            EncounterTable(slug="x", dice="1d6", entries=[])


class TestFactionDef:
    def test_stance_bounds(self):
        with pytest.raises(ValidationError):
            FactionDef(
                slug="guild",
                name="Guild",
                relations={"council": {"stance": -11, "label": "war"}},
            )

    def test_valid_faction(self):
        faction = FactionDef(
            slug="guild",
            name="Guild",
            goals=["monopoly"],
            relations={"council": {"stance": -8, "label": "trade war"}},
            resources=[{"name": "gold", "quantity": 5000}],
        )
        assert faction.relations["council"].stance == -8
