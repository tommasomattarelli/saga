from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.storage_support import (
    history_fixture as history_fixture,  # noqa: F401
)


@pytest.mark.asyncio
async def test_journal_retrieval_from_turns(
    auth_client: AsyncClient, history_fixture: HistoryFixture
):
    """Verify that the journal correctly retrieves data from the turns table."""
    fixture = history_fixture
    campaign_id = fixture.campaign.id
    turn1 = Turn(
        id=uuid4(),
        campaign_id=campaign_id,
        continuation_id=fixture.root.id,
        history_depth=1,
        turn_number=1,
        player_action="I enter the cave.",
        narration="The cave is dark and damp.",
        model_used="test",
    )
    turn2 = Turn(
        id=uuid4(),
        campaign_id=campaign_id,
        continuation_id=fixture.root.id,
        parent_turn_id=turn1.id,
        history_depth=2,
        turn_number=2,
        player_action="I light a torch.",
        narration="The shadows dance on the walls.",
        model_used="test",
    )
    fixture.session.add_all([turn1, turn2])
    fixture.campaign.active_head_turn_id = turn2.id
    fixture.campaign.turn_number = 2
    await fixture.session.commit()

    # 3. Get Journal via API
    response = await auth_client.get(f"/api/journal/{campaign_id}")
    assert response.status_code == 200
    journal = response.json()

    # Check that it returns turns in descending order (usually)
    assert len(journal) == 2
    assert journal[0]["turn_number"] == 2
    assert journal[0]["player_action"] == "I light a torch."
    assert journal[1]["turn_number"] == 1
