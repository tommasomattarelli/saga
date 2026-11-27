"""Tests for the ADR 0023 relational-graph configuration."""

import pytest
from pydantic import ValidationError

from app.memory.graph_config import GraphConfig, get_graph_config


class TestGraphConfig:
    def test_loads_shipped_defaults(self):
        config = get_graph_config()
        assert config.max_relations == 200
        assert config.prominent_max_relations == 12
        assert config.scene_max_relations == 20
        assert config.extract_max_per_batch == 8
        kinds = {kind.kind: kind.prominent for kind in config.default_relation_kinds}
        assert kinds["companion"] is True
        assert kinds["ally"] is False

    @pytest.mark.parametrize(
        "payload",
        [
            {"unknown": 1},
            {"max_relations": 0},
            {"prominent_max_relations": 201},
            {"scene_max_relations": 201},
            {"extract_max_per_batch": 201},
            {"default_relation_kinds": [{"kind": "ally", "prominent": "yes"}]},
            {"default_relation_kinds": [{"kind": "ally"}, {"kind": "ally"}]},
        ],
    )
    def test_rejects_invalid_values(self, payload):
        with pytest.raises(ValidationError):
            GraphConfig.model_validate(payload)
