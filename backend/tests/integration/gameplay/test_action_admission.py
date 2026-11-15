from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.memory.job_claim_transitions import INCOMPATIBLE_JOB_REASON
from app.memory.job_claims import claim_job, fail_claim
from app.memory.job_worker import run_memory_pass
from app.memory.production_policy import configured_memory_policy
from app.models.campaign import Campaign
from app.models.memory_job import MemoryJob, MemoryJobTerminalReason
from app.models.turn import Turn
from app.models.turn_request import TurnRequest
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result
from tests.integration.gameplay.test_memory_pipeline_cutover import PipelineProvider

pytestmark = pytest.mark.usefixtures("configured_generation")


class TypedMemoryPipelineProvider(PipelineProvider):
    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.check()
        self.memory_prompts.append(request.system_prompt)
        text = {
            "summary": '{"text":"INTERMEDIATE: The courier carries a sealed letter."}',
            "facts": '{"facts":[]}',
            "global": (
                '{"story_so_far":"REMOTE: The courier arrived.",'
                '"open_threads":["A sealed letter"],"relationships":[],"resolved_threads":[]}'
            ),
        }[request.role]
        return RawGenerationReceipt(text=text, raw_candidate=text)


async def full_raw_history(client, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict]:
    monkeypatch.setattr("app.api.rate_limit.limiter.enabled", False)
    policy = configured_memory_policy()
    fast = policy.model_copy(
        update={
            "admission": policy.admission.model_copy(update={"wait_timeout_seconds": 0.02}),
        }
    )
    monkeypatch.setattr("app.memory.campaign_history.configured_memory_policy", lambda: fast)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    campaign_id, body = await campaign_and_action(client)
    for _ in range(16):
        response = await client.post(f"/api/campaigns/{campaign_id}/action", json=body)
        assert response.status_code == 200, response.text
        body = {
            **body,
            "request_id": str(uuid4()),
            "expected_head_turn_id": response.json()["head_turn_id"],
        }
    return campaign_id, body


async def test_raw_ceiling_waits_without_claim_then_same_request_can_resume(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    assert_no_db_held,
) -> None:
    campaign_id, body = await full_raw_history(auth_client, monkeypatch)
    response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "memory_busy"
    assert await db_session.scalar(select(func.count()).select_from(TurnRequest)) == 16
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 16
    campaign = await db_session.get(Campaign, UUID(campaign_id))
    assert campaign is not None and campaign.turn_number == 16
    await db_session.close()
    provider = TypedMemoryPipelineProvider(assert_no_db_held)
    monkeypatch.setattr(
        "app.memory.job_execution.get_provider", lambda *_args, **_kwargs: provider
    )
    assert await run_memory_pass(UUID(campaign_id)) == 1
    resumed = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert resumed.status_code == 200
    assert resumed.json()["request_id"] == body["request_id"]
    assert resumed.json()["turn_number"] == 17


@pytest.mark.parametrize(
    ("state", "code", "message"),
    [
        (
            "manual_retry_required",
            "memory_retry_required",
            "Memory processing needs an explicit retry to continue.",
        ),
        (
            "exhausted",
            "memory_busy",
            "Memory processing exhausted its generation budget and cannot be retried.",
        ),
    ],
)
async def test_capacity_reports_retryability_without_mislabeling_exhaustion(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    code: str,
    message: str,
) -> None:
    campaign_id, body = await full_raw_history(auth_client, monkeypatch)
    job = await db_session.scalar(select(MemoryJob))
    assert job is not None
    job.state = state
    if state == "exhausted":
        job.terminal_at = datetime.now(UTC)
        job.terminal_reason = MemoryJobTerminalReason.REQUIRED_RESULT_SEND_BUDGET_EXHAUSTED
    await db_session.commit()

    response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert response.status_code == 503
    assert response.json()["detail"] == {"code": code, "message": message}


async def test_blocked_memory_requires_explicit_retry_without_resetting_attempt_history(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await full_raw_history(auth_client, monkeypatch)
    job = await db_session.scalar(select(MemoryJob))
    assert job is not None
    claim = await claim_job(db_session, UUID(campaign_id), job.id)
    assert claim is not None
    await fail_claim(db_session, claim, configuration_required=True)
    await db_session.commit()
    blocked = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert blocked.status_code == 503
    assert blocked.json()["detail"]["code"] == "memory_configuration_required"
    await db_session.refresh(job)
    assert job.state == "blocked" and job.attempt_count == 1
    retry = await auth_client.post(
        f"/api/campaigns/{campaign_id}/memory/retry",
        json={
            "expected_head_turn_id": body["expected_head_turn_id"],
            "expected_context_epoch": 0,
        },
    )
    assert retry.status_code == 200 and retry.json()["retried"] == 1
    await db_session.refresh(job)
    assert job.state == "queued" and job.retry_cycle == 1 and job.attempt_count == 1


async def test_integrity_block_is_not_misreported_as_configuration_or_retried(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await full_raw_history(auth_client, monkeypatch)
    job = await db_session.scalar(select(MemoryJob))
    assert job is not None
    job.state = "blocked"
    job.last_error = INCOMPATIBLE_JOB_REASON
    await db_session.commit()

    response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "memory_retry_required",
        "message": (
            "Saved memory contracts or history are incompatible; provider changes or retries "
            "cannot repair this job."
        ),
    }
    monkeypatch.setattr("app.api.memory.wake_memory_worker", lambda: None)
    retry = await auth_client.post(
        f"/api/campaigns/{campaign_id}/memory/retry",
        json={
            "expected_head_turn_id": body["expected_head_turn_id"],
            "expected_context_epoch": 0,
        },
    )
    assert retry.status_code == 200
    assert retry.json() == {"retried": 0}
    await db_session.refresh(job)
    assert job.state == "blocked"
