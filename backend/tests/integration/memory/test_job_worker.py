import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.memory.job_worker import _campaign_intervals, run_memory_pass, run_memory_worker
from app.models.memory_document import MemorySummary
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from tests.integration.memory.job_support import configure_local_generation
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_execution import ControlledProvider
from tests.integration.memory.test_job_publication import _claimed_job
from tests.integration.memory.test_job_scheduler import active_history


async def test_integrated_replay_persists_source_before_real_memory_jobs(
    auth_client,
    configured_generation,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    from eval.integrated_memory.replay import (
        authored_boundaries,
        create_replay_campaign,
        replay_sources,
    )
    from eval.integrated_memory.source_evidence import collect_batch_evidence
    from eval.memory_scenarios.build import build_scenario_async

    scenario = await build_scenario_async(batch_size=5)
    campaign_id = await create_replay_campaign(auth_client)

    class OfflineMemoryProvider:
        async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
            raw = (
                '{"story_so_far":"The key promise was fulfilled.","open_threads":[],"relationships":[],"resolved_threads":[]}'
                if request.role == "global"
                else '{"facts":[]}'
                if request.role == "facts"
                else '{"text":"The recorded events preserve the campaign history."}'
            )
            return RawGenerationReceipt(text=raw, raw_candidate=raw)

    from app.ai.providers import base
    from app.ai.router import get_local_endpoints

    for endpoint_url in get_local_endpoints().values():
        monkeypatch.setitem(
            base._providers,
            ("local", None, endpoint_url),
            OfflineMemoryProvider(),
        )

    async def drain() -> None:
        await run_memory_pass(campaign_id)

    async with authored_boundaries(scenario.sources):
        evidence = await replay_sources(
            auth_client,
            campaign_id,
            scenario.sources,
            after_turn=drain,
        )

    assert len(evidence) == 52
    assert sum(len(turn.operations) for turn in evidence) == sum(
        len(turn.operations or ()) for turn in scenario.sources.turns
    )
    batches = await collect_batch_evidence(campaign_id, evidence)
    assert len(batches) == 11
    assert all(batch.source_turn_ids for batch in batches)
    jobs = list(
        await db_session.scalars(select(MemoryJob).where(MemoryJob.campaign_id == campaign_id))
    )
    assert len([job for job in jobs if job.kind == "batch"]) == 11
    assert len([job for job in jobs if job.kind == "global"]) == 9
    assert all(job.state == "succeeded" for job in jobs)
    assert await run_memory_pass(campaign_id) == 0


async def test_integrated_replay_fsyncs_mapping_before_after_turn_failure(
    auth_client,
    configured_generation,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from eval.integrated_memory.replay import (
        authored_boundaries,
        create_replay_campaign,
        replay_sources,
    )
    from eval.memory_scenarios.build import build_scenario_async

    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    scenario = await build_scenario_async(batch_size=5)
    sources = scenario.sources.model_copy(update={"turns": scenario.sources.turns[:1]})
    campaign_id = await create_replay_campaign(auth_client)
    evidence_path = tmp_path / "turns.jsonl"

    async def fail_after_turn() -> None:
        raise RuntimeError("simulated driver failure")

    async with authored_boundaries(sources):
        with pytest.raises(RuntimeError, match="simulated driver failure"):
            await replay_sources(
                auth_client,
                campaign_id,
                sources,
                after_turn=fail_after_turn,
                evidence_path=evidence_path,
            )

    rows = [json.loads(line) for line in evidence_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["source_turn_id"] == str(sources.turns[0].turn_id)
    assert rows[0]["turn_id"]
    assert rows[0]["status"] == "verified"
    from app.models.turn import Turn

    persisted_ids = list(
        await db_session.scalars(select(Turn.id).where(Turn.campaign_id == campaign_id))
    )
    assert persisted_ids == [UUID(rows[0]["turn_id"])]


async def test_integrated_replay_records_committed_turn_when_source_equivalence_fails(
    auth_client,
    configured_generation,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from eval.integrated_memory.replay import (
        authored_boundaries,
        create_replay_campaign,
        replay_sources,
    )
    from eval.memory_scenarios.build import build_scenario_async

    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    scenario = await build_scenario_async(batch_size=5)
    authored = scenario.sources.turns[0].model_copy(update={"narration": "incorrect source"})
    sources = scenario.sources.model_copy(update={"turns": (authored,)})
    campaign_id = await create_replay_campaign(auth_client)
    evidence_path = tmp_path / "turns.jsonl"

    async def unexpected_after_turn() -> None:
        raise AssertionError("invalid evidence must stop before the driver callback")

    async with authored_boundaries(sources):
        with pytest.raises(AssertionError, match="persisted narration diverged"):
            await replay_sources(
                auth_client,
                campaign_id,
                sources,
                after_turn=unexpected_after_turn,
                evidence_path=evidence_path,
            )

    row = json.loads(evidence_path.read_text())
    assert row["source_turn_id"] == str(authored.turn_id)
    assert row["turn_id"]
    assert row["status"] == "invalid"
    assert "persisted narration diverged" in row["diagnostic"]


async def test_real_pipeline_cascades_original_batches_into_global(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    f = history_fixture
    await configure_local_generation(f)
    state = await active_history(f, 8)
    provider = ControlledProvider([])
    calls: list[tuple[str, str]] = []

    async def send(request: GenerationRequest) -> RawGenerationReceipt:
        prompt = str(request.messages[0]["content"])
        calls.append((request.system_prompt, prompt))
        if request.role == "global":
            assert '"previous"' in prompt
            assert '"player_action":"Action"' in prompt
            raw = '{"story_so_far":"The first batch.","open_threads":[],"relationships":[],"resolved_threads":[]}'
        elif request.role == "facts":
            raw = '{"facts":[]}'
        else:
            raw = '{"text":"Intermediate memory."}'
        return RawGenerationReceipt(text=raw, raw_candidate=raw)

    monkeypatch.setattr(provider, "send", send)
    monkeypatch.setattr(
        "app.memory.job_execution.get_provider", lambda *_args, **_kwargs: provider
    )
    for _ in range(5):
        await run_memory_pass(f.campaign.id)
    await f.session.refresh(state)
    assert state.global_checkpoint_id is not None
    jobs = list(await f.session.scalars(select(MemoryJob)))
    assert len([job for job in jobs if job.kind == "batch"]) == 3
    assert len([job for job in jobs if job.kind == "global"]) == 2
    assert all(job.state == "succeeded" for job in jobs)
    assert len(calls) == 8
    assert len(list(await f.session.scalars(select(MemorySummary)))) == 3
    saved_cursors = state.global_checkpoint_id, state.last_compacted_batch_id
    assert await run_memory_pass(f.campaign.id) == 0
    await f.session.refresh(state)
    assert saved_cursors == (state.global_checkpoint_id, state.last_compacted_batch_id)


async def test_worker_with_no_eligible_campaigns_stops_without_provider_work(
    history_fixture: HistoryFixture,
) -> None:
    stop, wake = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(run_memory_worker(stop, wake))
    stop.set()
    await asyncio.wait_for(task, timeout=2)


async def test_worker_discovers_terminal_payloads_without_active_memory_state(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    job, _, generations, _, _ = await _claimed_job(fixture)
    job.state = "succeeded"
    job.claim_token = None
    job.lease_expires_at = None
    job.terminal_at = datetime.now(UTC) - timedelta(days=1)
    fixture.campaign.active_memory_state_id = None
    await fixture.session.commit()

    assert fixture.campaign.id in await _campaign_intervals()
    await run_memory_pass(fixture.campaign.id)

    stored = list(
        await fixture.session.scalars(
            select(MemoryGeneration)
            .where(MemoryGeneration.id.in_([generation.id for generation in generations]))
            .execution_options(populate_existing=True)
        )
    )
    assert all(generation.raw_candidate is None for generation in stored)
    assert all(generation.receipt is None for generation in stored)
