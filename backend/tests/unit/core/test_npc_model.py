"""ADR 0009 S1 — engine contract model + B2 partition exhaustiveness."""

import pytest
from pydantic import ValidationError

from app.models.npc import IMMUTABLE_FIELDS, MUTABLE_FIELDS, NpcEngineRecord


class TestPartition:
    def test_every_field_classified_exactly_once(self):
        # B2: a new engine field must be added to exactly one of the two sets.
        model_fields = set(NpcEngineRecord.model_fields)
        assert model_fields == MUTABLE_FIELDS | IMMUTABLE_FIELDS
        assert not MUTABLE_FIELDS & IMMUTABLE_FIELDS

    def test_owned_domains_are_immutable(self):
        # 0005-owned + engine-owned fields must never be update_npc-writable.
        assert {"psychology", "met_player", "lifecycle", "slug"} <= IMMUTABLE_FIELDS


class TestNpcEngineRecord:
    def test_birth_defaults(self):
        npc = NpcEngineRecord(name="Lyra")
        assert npc.lifecycle == "alive"
        assert npc.condition is None
        assert npc.slug is None
        assert npc.met_player is False
        assert npc.traits == {}

    def test_lifecycle_closed_enum(self):
        with pytest.raises(ValidationError):
            NpcEngineRecord(name="Lyra", lifecycle="sleeping")

    def test_unknown_engine_field_rejected(self):
        # Ghost fields are the drift this model exists to stop.
        with pytest.raises(ValidationError):
            NpcEngineRecord(name="Lyra", disposition=10)

    def test_traits_hold_descriptives(self):
        npc = NpcEngineRecord(name="Lyra", slug="lyra", traits={"role": "Ranger"})
        assert npc.traits["role"] == "Ranger"
