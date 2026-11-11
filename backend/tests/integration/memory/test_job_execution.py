import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select

from app import dependencies
from app.ai.generation_attempt import generation_attempt_is_single
from app.ai.providers.base import AIProvider
from app.ai.router import ModelConfig
from app.memory.job_execution import execute_job
from app.memory.job_scheduler import coordinate_memory
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemorySummary
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_scheduler import active_history


class ControlledProvider(AIProvider):
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "test",
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        assert generation_attempt_is_single()
        async with dependencies.async_session() as db:
            provenance = list(await db.scalars(select(MemoryGeneration)))
            assert len(provenance) == len(self.calls) + 1
            assert provenance[-1].attempt_id is not None
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
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    provider = ControlledProvider(['{"text":"A durable memory."}', facts])

    async def resolve(owner):
        assert owner == f.campaign.user_id
        return provider, ModelConfig(provider="local", model="test-model", max_tokens=500)

    monkeypatch.setattr("app.memory.job_execution.get_user_generation", resolve)
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

    original_generate = provider.generate

    async def assert_no_session(**kwargs):
        assert sessions_in_use == 0
        return await original_generate(**kwargs)

    monkeypatch.setattr(provider, "generate", assert_no_session)
    monkeypatch.setattr(dependencies, "async_session", tracked_session)
    published = await execute_job(f.campaign.id, job_id)
    assert published == (facts == '{"facts":[]}')
    assert len(provider.calls) == 2
    assert not generation_attempt_is_single()
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None
    assert job.state == ("succeeded" if published else "retry_wait")
    assert await f.session.scalar(select(func.count()).select_from(MemorySummary)) == int(
        published
    )
    assert await f.session.scalar(select(func.count()).select_from(MemoryGeneration)) == 2
    attempts = list(await f.session.scalars(select(MemoryJobAttempt)))
    assert len(attempts) == 1
    assert attempts[0].state == ("succeeded" if published else "failed")


async def test_missing_credentials_blocks_without_reserving_provider_calls(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.exceptions import ValidationError

    f = history_fixture
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()

    async def missing(owner):
        raise ValidationError("Sensitive internal credential details")

    monkeypatch.setattr("app.memory.job_execution.get_user_generation", missing)
    assert not await execute_job(f.campaign.id, job_id)
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None and job.state == "blocked"
    assert "Sensitive" not in (job.last_error or "")
    assert await f.session.scalar(select(func.count()).select_from(MemoryGeneration)) == 0


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
    await active_history(f, 4)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    provider = ControlledProvider(['{"text":"A partial candidate."}', '{"facts":[]}'])
    original_generate = provider.generate
    cancelled = asyncio.Event()

    async def delayed(**kwargs):
        result = await original_generate(**kwargs)
        try:
            await asyncio.sleep(1.2)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return result

    async def resolve(owner):
        return provider, ModelConfig(provider="local", model="test-model", max_tokens=500)

    monkeypatch.setattr(provider, "generate", delayed)
    monkeypatch.setattr("app.memory.job_execution.get_user_generation", resolve)
    assert not await execute_job(f.campaign.id, job_id)
    assert len(provider.calls) == 2 and cancelled.is_set()
    job = await f.session.get(MemoryJob, job_id, populate_existing=True)
    assert job is not None and job.attempt_count == 1 and job.state == "retry_wait"
    assert await f.session.scalar(select(func.count()).select_from(MemorySummary)) == 0
