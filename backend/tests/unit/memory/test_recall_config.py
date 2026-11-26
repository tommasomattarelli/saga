"""Tests for the ADR 0022 retrieval configuration."""

import pytest
from pydantic import ValidationError

from app.config_loader import load_saga_config
from app.memory.recall_config import RecallConfig, get_recall_config


class TestRecallConfig:
    def test_loads_shipped_defaults(self):
        assert load_saga_config()["recall"]["candidate_pool"] == 25
        config = get_recall_config()
        assert config.enabled is True
        assert config.candidate_pool == 25
        assert config.inject_limit == 5
        assert config.max_critical_inject == 5
        assert config.query.recent_narration_turns == 2
        assert config.dedup.enabled is True

    def test_accepts_explicit_values(self):
        config = RecallConfig.model_validate(
            {
                "rrf_k": 10,
                "boosts": {"critical": 0.5},
                "dedup": {"similarity_threshold": 0.9},
            }
        )
        assert config.rrf_k == 10
        assert config.boosts.critical == 0.5
        assert config.dedup.similarity_threshold == 0.9

    @pytest.mark.parametrize(
        "payload",
        [
            {"unknown": 1},
            {"inject_limit": 0},
            {"boosts": {"critical": -1}},
            {"dedup": {"similarity_threshold": 1.5}},
            {"inject_limit": 30},
            {"max_critical_inject": 6},
        ],
    )
    def test_rejects_invalid_values(self, payload):
        with pytest.raises(ValidationError):
            RecallConfig.model_validate(payload)
