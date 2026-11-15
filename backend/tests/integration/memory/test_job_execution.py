import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app import dependencies
from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.providers.base import AIProvider
from app.memory.job_execution import execute_job
from app.memory.job_scheduler import coordinate_memory
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemorySummary
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.job_support import (
    configure_local_generation,
    configure_openrouter_generation,
)
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_scheduler import active_history


class ControlledProvider(AIProvider):
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        async with dependencies.async_session() as db:
            pending = list(
                await db.scalars(select(MemoryGeneration).where(MemoryGeneration.status.is_(None)))
            )
            assert len(pending) == 1
            assert pending[0].role == request.role
        self.calls.append(request.role)
        raw = self.replies.pop(0)
        return RawGenerationReceipt(text=raw, raw_candidate=raw)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "test",
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(system_prompt)
        return self.replies.pop(0)

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "test",
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        yield ""

    async def embed(self, text: str, model: str = "test") -> list[float]:
        raise AssertionError("Publication queues embeddings without contacting a provider")


@pytest.mark.parametrize("facts", ['{"facts":[]}', '{"wrong":[]}'])
async def test_execution_reserves_calls_and_only_publishes_complete_split_results(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
    facts: str,
) -> None:
    f = history_fixture
    await configure_local_generation(f)
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    replies = ['{"text":"A durable memory."}', facts]
    if facts != '{"facts":[]}':
        replies.extend([facts, facts])
    provider = ControlledProvider(replies)
    monkeypatch.setattr(
        "app.memory.job_execution.get_provider", lambda *_args, **_kwargs: provider
    )
    original = dependencies.async_session
    sessions_in_use = 0

    @asynccontextmanager
    async def tracked_session():
        nonlocal sessions_in_use
        async with original() as db:
            sessions_in_use += 1
            try:
                yield db
            finally:
                sessions_in_use -= 1

    original_send = provider.send

    async def assert_no_session(request):
        assert sessions_in_use == 0
        return await original_send(request)

    monkeypatch.setattr(provider, "send", assert_no_session)
    monkeypatch.setattr(dependencies, "async_session", tracked_session)
    published = await execute_job(f.campaign.id, job_id)
    assert published == (facts == '{"facts":[]}')
    assert len(provider.calls) == (2 if published else 4)
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None
    assert job.state == ("succeeded" if published else "retry_wait")
    assert await f.session.scalar(select(func.count()).select_from(MemorySummary)) == int(
        published
    )
    assert await f.session.scalar(select(func.count()).select_from(MemoryGeneration)) == (
        2 if published else 4
    )
    attempts = list(await f.session.scalars(select(MemoryJobAttempt)))
    assert len(attempts) == 1
    assert attempts[0].state == ("succeeded" if published else "failed")


async def test_missing_credentials_blocks_without_reserving_provider_calls(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    assert not await execute_job(f.campaign.id, job_id)
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None and job.state == "blocked"
    assert job.execution_identity is None
    assert job.attempt_count == 0
    assert await f.session.scalar(select(func.count()).select_from(MemoryGeneration)) == 0


async def test_affinity_toggle_blocks_before_io_and_retry_keeps_frozen_identity(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory import job_claims, job_execution

    f = history_fixture
    await configure_openrouter_generation(f, model="test-model:free")
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None and job.execution_identity is not None
    identity = job.execution_identity.model_dump(mode="json")
    identity_hash = job.execution_identity_hash
    assert job.execution_identity.result_identities["summary"].session_affinity == str(
        f.campaign.id
    )
    provider_resolutions = 0

    def no_provider(*_args, **_kwargs):
        nonlocal provider_resolutions
        provider_resolutions += 1
        raise AssertionError("an incompatible affinity toggle must stop before provider setup")

    disabled = {"generation": {"openrouter_session_affinity": False}}
    enabled = {"generation": {"openrouter_session_affinity": True}}
    monkeypatch.setattr(job_execution, "get_provider", no_provider)
    monkeypatch.setattr(job_execution, "load_saga_config", lambda: disabled)
    assert not await execute_job(f.campaign.id, job_id)
    await f.session.refresh(job)
    assert job.state == "blocked"
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 0, 1)
    assert job.execution_identity is not None
    assert job.execution_identity.model_dump(mode="json") == identity
    assert job.execution_identity_hash == identity_hash
    assert provider_resolutions == 0
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
        )
        == 0
    )

    monkeypatch.setattr(job_claims, "load_saga_config", lambda: disabled)
    assert not await job_claims.retry_job(f.session, f.campaign.id, job_id)
    await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "blocked"
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 0, 1)

    monkeypatch.setattr(job_claims, "load_saga_config", lambda: enabled)
    assert await job_claims.retry_job(f.session, f.campaign.id, job_id)
    await f.session.commit()
    await f.session.refresh(job)
    assert job.state == "queued"
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 1, 0)
    assert job.execution_identity is not None
    assert job.execution_identity.model_dump(mode="json") == identity
    assert job.execution_identity_hash == identity_hash
    assert provider_resolutions == 0


@pytest.mark.parametrize("change", ["model", "destination"])
async def test_changed_generation_identity_blocks_before_io_without_budget_reset(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from app.memory import job_claims, job_execution

    f = history_fixture
    user = await configure_local_generation(f)
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None and job.execution_identity is not None
    identity_hash = job.execution_identity_hash

    if change == "model":
        user.generation_model = "changed-model"
        await f.session.flush()
    else:
        await configure_openrouter_generation(f, model="test-model:free")
    await f.session.commit()

    provider_resolutions = 0

    def no_provider(*_args, **_kwargs):
        nonlocal provider_resolutions
        provider_resolutions += 1
        raise AssertionError("changed frozen generation settings must stop before provider setup")

    monkeypatch.setattr(job_execution, "get_provider", no_provider)
    assert not await execute_job(f.campaign.id, job_id)
    await f.session.refresh(job)
    assert job.state == "blocked"
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 0, 1)
    assert job.execution_identity_hash == identity_hash
    assert provider_resolutions == 0
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
        )
        == 0
    )
    assert not await job_claims.retry_job(f.session, f.campaign.id, job_id)
    await f.session.commit()
    await f.session.refresh(job)
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 0, 1)
    assert job.execution_identity_hash == identity_hash


async def test_corrupt_job_manifest_is_blocked_as_integrity_failure(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.memory import job_execution

    f = history_fixture
    await configure_local_generation(f)
    await active_history(f, 4)
    monkeypatch.setattr("app.memory.job_scheduler.job_manifest_hash", lambda _manifest: "0" * 64)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None and job.execution_identity is not None
    identity = job.execution_identity.model_dump(mode="json")
    identity_hash = job.execution_identity_hash

    provider_resolutions = 0

    def no_provider(*_args, **_kwargs):
        nonlocal provider_resolutions
        provider_resolutions += 1
        raise AssertionError("an incompatible saved manifest must stop before provider setup")

    monkeypatch.setattr(job_execution, "get_provider", no_provider)
    assert not await execute_job(f.campaign.id, job_id)
    await f.session.refresh(job)
    assert job.state == "blocked"
    assert "incompatible" in (job.last_error or "").lower()
    assert "configuration" not in (job.last_error or "").lower()
    assert (job.attempt_count, job.retry_cycle, job.cycle_attempt_count) == (1, 0, 1)
    assert job.execution_identity is not None
    assert job.execution_identity.model_dump(mode="json") == identity
    assert job.execution_identity_hash == identity_hash
    assert provider_resolutions == 0
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemoryGeneration)
            .where(MemoryGeneration.job_id == job.id)
        )
        == 0
    )


@pytest.mark.parametrize("valid", [True, False])
async def test_integrated_driver_ledgers_real_job_calls_and_preserves_invalid_raw(
    history_fixture: HistoryFixture,
    tmp_path,
    assert_no_db_held,
    monkeypatch: pytest.MonkeyPatch,
    valid: bool,
) -> None:
    import json
    from uuid import uuid4

    import httpx
    import openai
    from eval.dialogue.limits import FreeRequestLimiter
    from eval.integrated_memory.job_driver import MemoryDriver
    from eval.integrated_memory.ledger import IntegratedLedger, LedgerBlockedError
    from eval.integrated_memory.plan import prepare_plan
    from eval.support.dialogue_affinity import session_id_for_model

    from app.ai.credentials import resolve_generation
    from app.ai.providers.local import LocalProvider
    from tests.integration.memory.job_support import configure_openrouter_generation

    f = history_fixture
    user = await configure_openrouter_generation(f, model="test-model:free")
    config, _, _ = resolve_generation(user)
    plan = prepare_plan(
        sources={
            "turns": [
                {
                    "reference": f"t{i}",
                    "turn_id": str(uuid4()),
                    "player_action": "Wait",
                    "narration": "Quiet.",
                    "operations": [],
                }
                for i in range(1, 13)
            ]
        },
        run_id="job-test",
        generation_model="test-model:free",
    )
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(
        f.session,
        f.campaign.id,
        session_scope=session_id_for_model(plan.session_scope, plan.generation_model or ""),
    )
    await f.session.commit()
    facts = '{"facts":[]}' if valid else '{"wrong":[]}'
    replies = ['{"text":"Integrated memory."}', facts]

    def respond(request: httpx.Request) -> httpx.Response:
        assert_no_db_held()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": replies.pop(0)}, "finish_reason": "stop"}]},
        )

    ledger = IntegratedLedger(
        tmp_path / "requests.jsonl",
        generation_cap=2,
        embedding_cap=0,
        text_cap=0,
        run_seal=plan.seal,
    )
    provider = object.__new__(LocalProvider)
    provider.provider_kind = "openrouter"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        provider.client = openai.AsyncOpenAI(
            api_key="offline", base_url="https://openrouter.ai/api/v1", http_client=http
        )

        async def resolve(owner):
            assert owner == f.campaign.user_id
            return provider, config

        driver = MemoryDriver(plan, ledger, f.campaign.id, tmp_path, resolve)
        monkeypatch.setattr(FreeRequestLimiter, "wait", AsyncMock(return_value=0.0))
        monkeypatch.setattr(
            "app.memory.job_execution.get_provider", lambda *_args, **_kwargs: provider
        )
        if valid:
            await driver._job(job_id)
        else:
            with pytest.raises(LedgerBlockedError):
                await driver._job(job_id)
    assert ledger.counts["generation"] == 2
    outputs = [json.loads(line) for line in (tmp_path / "outputs.jsonl").read_text().splitlines()]
    assert outputs[-1]["raw"] == facts
    assert outputs[-1]["valid"] is valid
    with pytest.raises(ValueError, match="before retrying"):
        await driver._job(job_id)


async def test_one_deadline_covers_both_specialists_and_persists_failure(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uuid import uuid4

    f = history_fixture
    payload = f.policy.payload.model_copy(
        update={
            "jobs": f.policy.payload.jobs.model_copy(update={"request_timeout_seconds": 2.0}),
        }
    )
    campaign = Campaign(
        id=uuid4(),
        user_id=f.campaign.user_id,
        name="Timeout",
        world_slug="test",
        difficulty=Difficulty.MEDIUM,
    )
    f.session.add(campaign)
    await f.session.flush()
    policy = MemoryPolicy(
        id=uuid4(),
        campaign_id=campaign.id,
        schema_version=1,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(id=uuid4(), campaign_id=campaign.id)
    f.session.add_all([policy, root])
    await f.session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await f.session.commit()
    f = HistoryFixture(f.session, campaign, policy, root)
    await configure_local_generation(f)
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    provider = ControlledProvider(['{"text":"A partial candidate."}', '{"facts":[]}'])
    original_send = provider.send
    cancelled = asyncio.Event()

    async def delayed(request):
        result = await original_send(request)
        try:
            await asyncio.sleep(1.2)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return result

    monkeypatch.setattr(provider, "send", delayed)
    monkeypatch.setattr(
        "app.memory.job_execution.get_provider", lambda *_args, **_kwargs: provider
    )
    assert not await execute_job(f.campaign.id, job_id)
    assert len(provider.calls) == 2 and cancelled.is_set()
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None and job.attempt_count == 1 and job.state == "retry_wait"
    assert await f.session.scalar(select(func.count()).select_from(MemorySummary)) == 0
