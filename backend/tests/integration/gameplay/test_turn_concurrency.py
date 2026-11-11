"""One campaign admits at most one in-flight action from a context snapshot."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.models.turn import Turn
from tests.action_support import action_body
from tests.integration.gameplay.test_turn_action import _create_campaign, _fake_state

pytestmark = pytest.mark.usefixtures("configured_generation")


@pytest.mark.asyncio
async def test_same_campaign_actions_serialize_to_one_success_and_one_conflict(
    auth_client, db_session
):
    campaign_id = await _create_campaign(auth_client)
    bodies = [await action_body(auth_client, campaign_id, f"action {index}") for index in range(5)]
    started = asyncio.Event()
    release = asyncio.Event()

    async def run_graph(*args, **kwargs):
        started.set()
        await release.wait()
        return _fake_state()

    with patch("app.api.turns.dm_graph.ainvoke", new=AsyncMock(side_effect=run_graph)):
        first_request = asyncio.create_task(
            auth_client.post(f"/api/campaigns/{campaign_id}/action", json=bodies[0])
        )
        await started.wait()
        rejected = await asyncio.gather(
            *(
                auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
                for body in bodies[1:]
            )
        )
        release.set()
        first_response = await first_request

    assert first_response.status_code == 200, first_response.text
    assert [response.status_code for response in rejected] == [409] * 4
    assert all(response.json()["detail"]["code"] == "action_in_progress" for response in rejected)
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Turn).where(Turn.campaign_id == campaign_id)
        )
        == 1
    )
