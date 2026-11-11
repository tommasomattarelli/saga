from uuid import UUID

import pytest
from sqlalchemy import event, func, select, text

from app import dependencies
from app.models.campaign import Campaign
from app.models.save import Save
from app.models.turn import Turn
from tests.integration.gameplay.test_action_requests import campaign_and_action, graph_result

pytestmark = pytest.mark.usefixtures("configured_generation")


async def test_expiry_immediately_before_request_transition_rolls_back_publication(
    auth_client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, body = await campaign_and_action(auth_client)

    async def generate(state, **kwargs):
        return graph_result(state)

    monkeypatch.setattr("app.api.turns.dm_graph.ainvoke", generate)
    expired = False

    def expire_before_transition(connection, cursor, statement, parameters, context, executemany):
        nonlocal expired
        if not expired and statement.lower().startswith("update turn_requests"):
            expired = True
            connection.execute(
                text(
                    "UPDATE turn_requests SET execution_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE campaign_id=:campaign_id AND state='running'"
                ),
                {"campaign_id": UUID(campaign_id)},
            )

    event.listen(
        dependencies.engine.sync_engine, "before_cursor_execute", expire_before_transition
    )
    try:
        response = await auth_client.post(f"/api/campaigns/{campaign_id}/action", json=body)
    finally:
        event.remove(
            dependencies.engine.sync_engine, "before_cursor_execute", expire_before_transition
        )
    assert expired and response.status_code == 409
    assert response.json()["detail"]["code"] == "action_context_changed"
    assert await db_session.scalar(select(func.count()).select_from(Turn)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Save)) == 0
    campaign = await db_session.get(Campaign, UUID(campaign_id), populate_existing=True)
    assert campaign is not None and campaign.active_head_turn_id is None
