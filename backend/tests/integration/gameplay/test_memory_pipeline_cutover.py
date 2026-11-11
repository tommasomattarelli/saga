from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse
from app.ai.router import ModelConfig
from app.memory.job_worker import run_memory_pass
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_job import MemoryJob
from app.models.source_embedding import SourceEmbedding
from app.models.turn import Turn

pytestmark = pytest.mark.usefixtures("configured_generation")


class PipelineProvider(AIProvider):
    def __init__(self, check: Callable[[], None]) -> None:
        self.check = check
        self.dm_prompts: list[str] = []
        self.memory_prompts: list[str] = []

    async def generate(self, system_prompt, messages, **kwargs):
        self.check()
        self.memory_prompts.append(system_prompt)
        if '"resolved_threads"' in system_prompt:
            return (
                '{"story_so_far":"REMOTE: The courier arrived.",'
                '"open_threads":["A sealed letter"],"relationships":[],"resolved_threads":[]}'
            )
        if '"facts"' in system_prompt:
            return '{"facts":[]}'
        return '{"text":"INTERMEDIATE: The courier carries a sealed letter."}'

    async def generate_with_tools(self, system_prompt, messages, **kwargs):
        self.check()
        self.dm_prompts.append(system_prompt)
        return AgentResponse(text="The courier waits beside the gate.")

    async def stream(self, system_prompt, messages, model, max_tokens=2000) -> AsyncIterator[str]:
        raise AssertionError("This test must not stream provider requests")
        yield ""


async def test_real_api_graph_worker_and_prompt_use_three_disjoint_levels(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    assert_no_db_held,
) -> None:
    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    provider = PipelineProvider(assert_no_db_held)

    async def resolve(owner):
        return provider, ModelConfig(
            provider="local", model="controlled-pipeline", max_tokens=2000
        )

    monkeypatch.setattr("app.core.dm.dm_nodes.get_user_generation", resolve)
    monkeypatch.setattr("app.memory.job_execution.get_user_generation", resolve)
    created = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "Full pipeline",
            "difficulty": "medium",
        },
    )
    assert created.status_code == 201
    campaign = created.json()
    head = None
    for number in range(1, 22):
        response = await auth_client.post(
            f"/api/campaigns/{campaign['id']}/action",
            json={
                "action": f"Wait for the courier, step {number}",
                "request_id": str(uuid4()),
                "expected_head_turn_id": head,
                "expected_context_epoch": 0,
            },
        )
        assert response.status_code == 200, response.text
        head = response.json()["head_turn_id"]
        await run_memory_pass(UUID(campaign["id"]))
    assert "REMOTE: The courier arrived." in provider.dm_prompts[-1]
    assert "INTERMEDIATE: The courier carries a sealed letter." in provider.dm_prompts[-1]
    assert await db_session.scalar(select(func.count()).select_from(MemorySummary)) == 3
    assert await db_session.scalar(select(func.count()).select_from(MemoryGlobalCheckpoint)) == 1
    state = await db_session.scalar(select(MemoryState))
    assert state is not None and state.global_checkpoint_id is not None
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 21
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Turn).where(Turn.summary.is_not(None))
        )
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(SourceEmbedding)) == 0
    assert all(job.state == "succeeded" for job in await db_session.scalars(select(MemoryJob)))
