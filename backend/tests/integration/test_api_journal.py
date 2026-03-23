import pytest
from httpx import AsyncClient

from app.models.turn import Turn


@pytest.mark.asyncio
async def test_journal_retrieval_from_turns(auth_client: AsyncClient, db_session):
    """Verify that the journal correctly retrieves data from the turns table."""
    # 1. Setup: Campaign
    camp_resp = await auth_client.post(
        "/api/campaigns",
        json={
            "name": "Journal Test",
            "template_id": "tutorial",
            "death_mode": "destino",
            "character_data": {"name": "Scribe"},
        },
    )
    campaign_id = camp_resp.json()["id"]

    # 2. Insert dummy turns directly into DB
    turn1 = Turn(
        campaign_id=campaign_id,
        turn_number=1,
        player_action="I enter the cave.",
        narration="The cave is dark and damp.",
        model_used="gpt-4o",
        importance_score=5,
    )
    turn2 = Turn(
        campaign_id=campaign_id,
        turn_number=2,
        player_action="I light a torch.",
        narration="The shadows dance on the walls.",
        model_used="gpt-4o",
        importance_score=5,
    )
    db_session.add_all([turn1, turn2])
    await db_session.commit()

    # 3. Get Journal via API
    response = await auth_client.get(f"/api/journal/{campaign_id}")
    assert response.status_code == 200
    journal = response.json()

    # Check that it returns turns in descending order (usually)
    assert len(journal) == 2
    assert journal[0]["turn_number"] == 2
    assert journal[0]["player_action"] == "I light a torch."
    assert journal[1]["turn_number"] == 1
