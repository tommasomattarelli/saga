import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.action_policy import ActionPolicy
from app.models.turn import Turn
from app.models.turn_request import TurnRequest
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result

pytestmark = pytest.mark.usefixtures("configured_generation")


async def test_committed_old_result_is_historical_after_another_action(
    auth_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    calls = 0

    async def generate(state, **kwargs):
        nonlocal calls
        calls += 1
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    first = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert first.status_code == 200
    following = {
        **body,
        "request_id": str(uuid4()),
        "expected_head_turn_id": first.json()["turn_id"],
    }
    second = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=following)
    assert second.status_code == 200
    historical = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert historical.status_code == 409 and calls == 2
    detail = historical.json()["detail"]
    assert detail["code"] == "action_context_changed"
    assert detail["result_turn_id"] == first.json()["turn_id"] and detail["refresh_required"]


async def test_graph_timeout_interrupts_without_automatic_paid_retry(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)
    cancelled = asyncio.Event()
    calls = 0
    policy = ActionPolicy(
        timeout_seconds=0.02,
        completion_margin_seconds=50.0,
        proxy_margin_seconds=80.0,
        admission_wait_seconds=10.0,
    )
    monkeypatch.setattr("app.api.turns.get_action_policy", lambda: policy)

    async def generate(state, **kwargs):
        nonlocal calls
        calls += 1
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    timed_out = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert timed_out.status_code == 504
    assert timed_out.json()["detail"]["code"] == "action_timeout"
    assert cancelled.is_set()
    repeated = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    assert repeated.status_code == 409 and calls == 1
    assert repeated.json()["detail"]["code"] == "action_interrupted"
    request = await db_session.get(TurnRequest, UUID(body["request_id"]))
    assert request is not None and request.state == "interrupted"
    assert request.execution_token is None and request.execution_expires_at is None
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 0
