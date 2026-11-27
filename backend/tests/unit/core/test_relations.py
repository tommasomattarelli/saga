"""ADR 0023 — shared relation-kind contract."""

from app.core.relations import relation_kind_default, relation_kind_defaults


def test_world_taxonomy_overrides_config_default():
    kinds = relation_kind_defaults({"relation_kinds": [{"kind": "ally", "prominent": True}]})
    assert kinds["ally"] is True
    assert kinds["companion"] is True


def test_unknown_kind_reports_candidates():
    default, candidates = relation_kind_default("bogus", {"ally": False})
    assert default is None
    assert candidates == ["ally"]
