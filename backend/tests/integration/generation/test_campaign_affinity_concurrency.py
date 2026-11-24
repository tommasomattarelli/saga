import asyncio
import json
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, Request

from app.ai.providers.local import LocalProvider
from app.core.dm.dm_graph import dm_graph
from tests.action_support import action_body
from tests.integration.generation.test_campaign_affinity import (
    affinity_client as affinity_client,
)
from tests.integration.generation.test_campaign_affinity import (
    configure,
)


async def test_concurrent_actions_in_one_campaign_share_the_same_session(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[Request]],
) -> None:
    provider, requests = affinity_client
    _, campaigns = await configure(auth_client)
    campaign = campaigns[0]
    bodies = [await action_body(auth_client, campaign, "Greet Lyra.") for _ in range(2)]
    graph_started = asyncio.Event()
    graph_finished = asyncio.Event()
    release = asyncio.Event()
    original_graph = dm_graph.ainvoke

    async def gated_graph(*args, **kwargs):
        graph_started.set()
        result = await original_graph(*args, **kwargs)
        graph_finished.set()
        await release.wait()
        return result

    with patch("app.api.turns.dm_graph.ainvoke", new=AsyncMock(side_effect=gated_graph)):
        first = asyncio.create_task(
            auth_client.post(f"/api/campaigns/{campaign}/action", json=bodies[0])
        )
        await graph_started.wait()
        await graph_finished.wait()
        second = await auth_client.post(f"/api/campaigns/{campaign}/action", json=bodies[1])
        release.set()
        first_response = await first
    assert [first_response.status_code, second.status_code] == [200, 409]
    assert second.json()["detail"]["code"] == "action_in_progress"
    assert len(requests) == 3
    assert {request.headers["x-session-id"] for request in requests} == {campaign}
    assert sum("tools" in json.loads(request.content) for request in requests) == 2
    assert "x-session-id" not in provider.client.default_headers
    assert provider.client.max_retries == 2
