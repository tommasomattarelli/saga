from app.memory.production_policy import configured_memory_policy


def test_configured_memory_policy_loads_complete_yaml_snapshot(monkeypatch):
    monkeypatch.setattr(
        "app.memory.production_policy.load_saga_config",
        lambda: {
            "memory": {
                "production": {
                    "raw_turns": 8,
                    "batch_turns": 4,
                    "intermediate_limit": 2,
                    "backlog_batches": 1,
                    "facts": {
                        "max_per_batch": 6,
                        "importance_levels": [
                            {
                                "name": "ordinary",
                                "criteria": "significant",
                                "examples": "agreement",
                            },
                            {
                                "name": "critical",
                                "criteria": "defining",
                                "examples": "betrayal",
                            },
                        ],
                    },
                    "global": {"target_words": 1000},
                    "jobs": {
                        "max_attempts": 4,
                        "retry_backoff_seconds": [5, 30, 120],
                        "request_timeout_seconds": 120,
                        "lease_seconds": 150,
                        "poll_seconds": 5,
                    },
                    "admission": {"wait_timeout_seconds": 10},
                }
            }
        },
    )

    policy = configured_memory_policy()

    assert policy.raw_turns == 8
    assert policy.batch_turns == 4
    assert policy.backlog_batches == 1
    assert policy.facts.max_per_batch == 6
    assert policy.global_.target_words == 1000
