import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from eval.dialogue.requests import SuiteProvider
from eval.support.ledger import BudgetExhaustedError, RequestLedger

from app.ai.providers.schemas import AgentResponse


async def test_parallel_actor_requests_are_reserved_and_captured_individually(tmp_path):
    provider = AsyncMock()
    ledger = RequestLedger(tmp_path / "calls.jsonl", budget=2)
    started = asyncio.Event()
    count = 0

    async def generate(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            started.set()
        await asyncio.wait_for(started.wait(), 1)
        assert ledger.spent == 2
        return '{"status":"silent","lines":[]}'

    provider.generate.side_effect = generate
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="actors",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=2,
    )
    await asyncio.gather(
        *[
            trace.generate("actor", [{"role": "user", "content": name}], "m:free")
            for name in ("A", "B")
        ]
    )
    assert ledger.spent == 2 and len(ledger.results()) == 2
    assert not ledger.interrupted()
    assert all(row.request and row.response for row in ledger.results())
    with pytest.raises(BudgetExhaustedError):
        await trace.generate("actor", [], "m:free")
    assert provider.generate.await_count == 2


async def test_transport_failure_is_counted_without_retry(tmp_path):
    provider = AsyncMock()
    provider.generate_with_tools.side_effect = RuntimeError("private transport internals")
    ledger = RequestLedger(tmp_path / "calls.jsonl", budget=1)
    trace = SuiteProvider(
        provider, ledger, key="trial", case="dm", model="m:free", run=0, commit="commit", ceiling=1
    )
    with pytest.raises(RuntimeError):
        await trace.generate_with_tools("dm", [], [], "m:free")
    assert ledger.spent == 1
    assert ledger.results()[0].status == "error"
    assert "private" not in ledger.results()[0].error
    assert ledger.results()[0].usage == []
    assert ledger.results()[0].correlation == {
        "role": "dm",
        "step": None,
        "beat": None,
        "npc_id": None,
        "npc_name": None,
    }
    assert provider.generate_with_tools.await_count == 1


async def test_dm_and_actor_calls_share_one_trial_and_daily_budget(tmp_path):
    provider = AsyncMock()
    provider.generate_with_tools.return_value = AgentResponse("A scene.")
    provider.generate.return_value = '{"status":"silent","lines":[]}'
    ledger = RequestLedger(tmp_path / "calls.jsonl", budget=2)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="beat",
        model="m:free",
        run=1,
        commit="commit",
        ceiling=7,
    )
    await trace.generate_with_tools("dm", [], [], "m:free")
    await trace.generate("npc", [], "m:free")
    assert trace.count == 2 and ledger.spent == 2
    assert [row.probe for row in ledger.results()] == ["beat:dm", "beat:actor"]


async def test_checkpoint_and_budget_reservation_failure(tmp_path):
    provider = AsyncMock()
    ledger = RequestLedger(tmp_path / "calls.jsonl", budget=0)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="case",
        model="m",
        run=0,
        commit="commit",
        ceiling=2,
        checkpoint="candidate-v2",
    )
    with pytest.raises(BudgetExhaustedError):
        await trace.generate("s", [], "m")
    assert trace.exhausted and trace.count == 0
    assert provider.generate.await_count == 0

    allowed = SuiteProvider(
        provider,
        RequestLedger(tmp_path / "allowed.jsonl", budget=1),
        key="trial",
        case="case",
        model="m",
        run=0,
        commit="commit",
        ceiling=1,
        checkpoint="candidate-v2",
    )
    provider.generate.return_value = "ok"
    await allowed.generate("s", [], "m")
    assert allowed.ledger.results()[0].checkpoint == "candidate-v2"


async def test_request_hash_covers_the_effective_prompt_tools_and_parameters(tmp_path):
    provider = AsyncMock()
    provider.generate.return_value = "ok"
    ledger = RequestLedger(tmp_path / "calls.jsonl", budget=1)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="case",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=1,
    )
    await trace.generate(
        "system",
        [{"role": "user", "content": "actual context"}],
        "m:free",
        max_tokens=321,
        json_mode=True,
    )
    row = ledger.results()[0]
    assert (
        row.request_hash
        == hashlib.sha256(json.dumps(row.request, sort_keys=True).encode()).hexdigest()
    )
