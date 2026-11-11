from uuid import uuid4

from httpx import AsyncClient


async def action_body(client: AsyncClient, campaign_id: str, action: str) -> dict[str, object]:
    response = await client.get(f"/api/campaigns/{campaign_id}")
    assert response.status_code == 200, response.text
    campaign = response.json()
    return {
        "action": action,
        "request_id": str(uuid4()),
        "expected_head_turn_id": campaign["active_head_turn_id"],
        "expected_context_epoch": campaign["context_epoch"],
    }
