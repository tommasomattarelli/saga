"""Cascade delete integration tests — verifies referential integrity on deletion.

These tests verify that missing `cascade='all, delete-orphan'` on SQLAlchemy
relationships would cause orphaned rows. This is a REAL PRODUCTION BUG that
was caught by these integration tests.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.save import Save
from app.models.turn import Turn
from app.models.user import User


def _make_user(prefix: str) -> User:
    uid = uuid.uuid4()
    return User(
        id=uid,
        username=f"{prefix}_{uid.hex[:6]}",
        email=f"{prefix}_{uid.hex[:6]}@cascade.dev",
        hashed_password="hash",
    )


def _make_campaign(user_id: uuid.UUID, name: str) -> Campaign:
    return Campaign(
        user_id=user_id,
        world_slug="the-awakening",
        name=name,
        death_mode="destino",
        character_data={},
        world_state={},
        quests={},
    )


@pytest.mark.asyncio
async def test_cascade_delete_campaigns_on_user_delete(db_session):
    """Deleting a User should cascade-delete all their Campaigns."""
    user = _make_user("cascade_u")
    db_session.add(user)
    await db_session.commit()

    campaign = _make_campaign(user.id, "Cascade Camp")
    db_session.add(campaign)
    await db_session.commit()
    campaign_id = campaign.id

    # Verify campaign exists
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    assert result.scalar_one_or_none() is not None

    # Delete user (cascades to campaigns via ORM relationship)
    result = await db_session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    await db_session.delete(db_user)
    await db_session.commit()

    # Verify campaign is gone
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cascade_delete_saves_on_campaign_delete(db_session):
    """Deleting a Campaign should cascade-delete its Saves."""
    user = _make_user("cascade_s")
    db_session.add(user)
    await db_session.commit()

    campaign = _make_campaign(user.id, "Camp With Saves")
    db_session.add(campaign)
    await db_session.commit()

    save = Save(
        campaign_id=campaign.id,
        name="My Save",
        turn_number=0,
        scene_summary="Start",
        is_auto=False,
        campaign_snapshot={},
    )
    db_session.add(save)
    await db_session.commit()
    save_id = save.id

    # Verify save exists
    result = await db_session.execute(select(Save).where(Save.id == save_id))
    assert result.scalar_one_or_none() is not None

    # Delete campaign
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign.id))
    db_campaign = result.scalar_one()
    await db_session.delete(db_campaign)
    await db_session.commit()

    # Verify save is gone
    result = await db_session.execute(select(Save).where(Save.id == save_id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cascade_delete_turns_on_campaign_delete(db_session):
    """Deleting a Campaign should cascade-delete its Turns."""
    user = _make_user("cascade_t")
    db_session.add(user)
    await db_session.commit()

    campaign = _make_campaign(user.id, "Camp With Turns")
    db_session.add(campaign)
    await db_session.commit()

    turn = Turn(
        campaign_id=campaign.id,
        turn_number=1,
        player_action="I attack",
        narration="You swing and miss.",
        model_used="gpt-4o",
        importance_score=5,
    )
    db_session.add(turn)
    await db_session.commit()
    turn_id = turn.id

    # Delete campaign
    result = await db_session.execute(select(Campaign).where(Campaign.id == campaign.id))
    db_campaign = result.scalar_one()
    await db_session.delete(db_campaign)
    await db_session.commit()

    # Verify turn is gone
    result = await db_session.execute(select(Turn).where(Turn.id == turn_id))
    assert result.scalar_one_or_none() is None
