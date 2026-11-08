import asyncio
import json

from httpx import AsyncClient, Request

from app.ai.providers.local import LocalProvider
from tests.integration.generation.test_campaign_affinity import (
    affinity_client as affinity_client,
)
from tests.integration.generation.test_campaign_affinity import (
    configure,
    drain_background,
)


async def test_concurrent_actions_in_one_campaign_share_the_same_session(
    auth_client: AsyncClient,
    affinity_client: tuple[LocalProvider, list[Request]],
) -> None:
    provider, requests = affinity_client
    _, campaigns = await configure(auth_client)
    campaign = campaigns[0]
    responses = await asyncio.gather(
        *[
            auth_client.post(f"/api/campaigns/{campaign}/action", json={"action": "Greet Lyra."})
            for _ in range(2)
        ]
    )
    await drain_background()
    assert [response.status_code for response in responses] == [200, 200]
    assert len(requests) == 8
    assert {request.headers["x-session-id"] for request in requests} == {campaign}
    assert sum("tools" in json.loads(request.content) for request in requests) == 4
    assert "x-session-id" not in provider.client.default_headers
    assert provider.client.max_retries == 2
