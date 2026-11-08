"""Integration tests for DELETE /api/campaigns/{id}."""

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.turn import Turn
from app.models.user import User


def _make_user() -> User:
    import uuid

    uid = uuid.uuid4()
    return User(
        id=uid,
        username=f"del_{uid.hex[:8]}",
        email=f"del_{uid.hex[:8]}@test.dev",
        hashed_password="hash",
        is_active=True,
    )


@pytest.mark.asyncio
async def test_delete_campaign_returns_204(auth_client, test_user):
    """DELETE /api/campaigns/{id} returns 204 for the owner."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "To Delete",
            "difficulty": "medium",
            "character_data": {},
        },
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    del_resp = await auth_client.delete(f"/api/campaigns/{campaign_id}")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_campaign_cascades_turns(auth_client, test_user, db_session):
    """Deleting a campaign also deletes its turns."""
    resp = await auth_client.post(
        "/api/campaigns",
        json={
            "world_id": "the-awakening",
            "name": "With Turns",
            "difficulty": "medium",
            "character_data": {},
        },
    )
    campaign_id = resp.json()["id"]

    import uuid

    turn = Turn(
        campaign_id=uuid.UUID(campaign_id),
        turn_number=1,
        player_action="I look around",
        narration="You see trees.",
        model_used="test",
        importance_score=3,
    )
    db_session.add(turn)
    await db_session.commit()
    turn_id = turn.id

    await auth_client.delete(f"/api/campaigns/{campaign_id}")

    result = await db_session.execute(select(Turn).where(Turn.id == turn_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_campaign_404_if_not_found(auth_client, test_user):
    """DELETE on unknown id returns 404."""
    import uuid

    resp = await auth_client.delete(f"/api/campaigns/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_campaign_403_if_not_owner(client, db_session):
    """DELETE returns 403 if another user tries to delete the campaign."""
    from app.security.auth import create_access_token

    # User A creates campaign
    user_a = _make_user()
    db_session.add(user_a)
    await db_session.commit()

    campaign = Campaign(
        user_id=user_a.id,
        world_slug="the-awakening",
        name="User A Campaign",
        difficulty="medium",
        character_data={},
        world_state={},
        quests={},
    )
    db_session.add(campaign)
    await db_session.commit()

    # User B tries to delete it
    user_b = _make_user()
    db_session.add(user_b)
    await db_session.commit()
    token_b = create_access_token(user_b.id)

    resp = await client.delete(
        f"/api/campaigns/{campaign.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
