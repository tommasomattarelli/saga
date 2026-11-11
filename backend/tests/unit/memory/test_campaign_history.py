import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.memory.campaign_history import (
    HistoryContractError,
    initialize_campaign_history,
    require_campaign_history,
)
from app.memory.production_policy import MemoryProductionPolicy
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemoryState


def configured_policy() -> dict:
    return {
        "raw_turns": 8,
        "batch_turns": 4,
        "intermediate_limit": 2,
        "backlog_batches": 1,
        "facts": {
            "max_per_batch": 6,
            "importance_levels": [
                {
                    "name": "ordinary",
                    "criteria": "significant detail",
                    "examples": "an agreement",
                },
                {
                    "name": "critical",
                    "criteria": "campaign-defining",
                    "examples": "a betrayal",
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


@pytest.mark.asyncio
async def test_initialize_campaign_history_creates_policy_root_and_empty_state(monkeypatch):
    monkeypatch.setattr(
        "app.memory.campaign_history.configured_memory_policy",
        lambda: MemoryProductionPolicy.model_validate(configured_policy()),
    )
    campaign = SimpleNamespace(
        id=uuid.uuid4(),
        memory_policy_id=None,
        active_continuation_id=None,
        active_head_turn_id=None,
        active_memory_state_id=None,
        context_epoch=0,
    )
    db = SimpleNamespace(add=Mock(), flush=AsyncMock())

    await initialize_campaign_history(db, campaign)

    rows = [call.args[0] for call in db.add.call_args_list]
    policy = next(row for row in rows if isinstance(row, MemoryPolicy))
    continuation = next(row for row in rows if isinstance(row, HistoryContinuation))
    state = next(row for row in rows if isinstance(row, MemoryState))
    assert policy.campaign_id == campaign.id
    assert policy.payload_hash == policy.payload.policy_hash()
    assert continuation.parent_continuation_id is None
    assert continuation.fork_head_turn_id is None
    assert state.context_epoch == 0
    assert state.global_checkpoint_id is None
    assert state.last_compacted_batch_id is None
    assert campaign.memory_policy_id == policy.id
    assert campaign.active_continuation_id == continuation.id
    assert campaign.active_memory_state_id == state.id
    assert campaign.active_head_turn_id is None


def test_require_campaign_history_rejects_pre_contract_campaign():
    campaign = SimpleNamespace(
        memory_policy_id=None,
        active_continuation_id=None,
        active_head_turn_id=None,
        active_memory_state_id=None,
    )

    with pytest.raises(HistoryContractError):
        require_campaign_history(campaign)


def test_require_campaign_history_accepts_initialized_campaign():
    campaign = SimpleNamespace(
        memory_policy_id=uuid.uuid4(),
        active_continuation_id=uuid.uuid4(),
        active_head_turn_id=None,
        active_memory_state_id=uuid.uuid4(),
    )

    require_campaign_history(campaign)
