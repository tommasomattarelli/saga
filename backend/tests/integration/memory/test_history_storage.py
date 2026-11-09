from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.memory.history import HistoryIntegrityError, history_path
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.save import Save
from tests.integration.memory.storage_support import HistoryFixture


async def test_ancestry_uses_completed_nodes_not_display_numbers(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn(number=1)
    second = await f.turn(first, number=4, narration="")
    old_future = await f.turn(second, number=8)
    branch = await f.fork(second)
    new_future = await f.turn(second, continuation=branch, number=8)
    path = await history_path(f.session, f.campaign.id, new_future.id)
    assert [turn.id for turn in path] == [first.id, second.id, new_future.id]
    assert old_future.id not in [turn.id for turn in path]
    assert [turn.history_depth for turn in path] == [1, 2, 3]
    assert await history_path(f.session, f.campaign.id, None) == []
    with pytest.raises(HistoryIntegrityError):
        await history_path(f.session, uuid4(), first.id)


@pytest.mark.parametrize(
    "assignment",
    [
        "history_depth=9",
        "parent_turn_id=id",
        "narration='rewritten'",
        "continuation_id=NULL",
        "player_action='rewritten'",
    ],
)
async def test_committed_history_is_immutable(
    history_fixture: HistoryFixture,
    assignment: str,
) -> None:
    f = history_fixture
    turn = await f.turn()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(f"UPDATE turns SET {assignment} WHERE id=:id"), {"id": turn.id}
        )
        await f.session.commit()
    await f.session.rollback()


async def test_parent_depth_and_continuation_entry_are_enforced(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    branch = await f.fork(first)
    with pytest.raises(IntegrityError):
        await f.turn(second, continuation=branch)
    await f.session.rollback()


async def test_history_cannot_reference_another_campaign(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    with pytest.raises(IntegrityError):
        f.session.add(HistoryContinuation(campaign_id=uuid4(), parent_continuation_id=f.root.id))
        await f.session.commit()
    await f.session.rollback()


async def test_save_freezes_references_not_a_live_memory_state(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    save = Save(
        campaign_id=f.campaign.id,
        name="Prefix",
        turn_number=1,
        scene_summary="Prefix",
        campaign_snapshot={},
        continuation_id=f.root.id,
        head_turn_id=first.id,
        memory_policy_id=f.policy.id,
    )
    f.session.add(save)
    await f.session.commit()
    await f.turn(first)
    assert save.head_turn_id == first.id
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE saves SET head_turn_id=NULL WHERE id=:id"), {"id": save.id}
        )
        await f.session.commit()
    await f.session.rollback()


async def test_history_cannot_be_deleted_without_deleting_campaign(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    with pytest.raises(IntegrityError):
        await f.session.execute(text("DELETE FROM turns WHERE id=:id"), {"id": first.id})
        await f.session.commit()
    await f.session.rollback()


async def test_a_campaign_has_one_history_root(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    f.session.add(HistoryContinuation(id=uuid4(), campaign_id=f.campaign.id))
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_a_campaign_has_one_immutable_policy_snapshot(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    f.session.add(
        MemoryPolicy(
            campaign_id=f.campaign.id,
            schema_version=1,
            payload=f.policy.payload,
            payload_hash=f.policy.payload_hash,
        )
    )
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_full_campaign_deletion_keeps_no_shared_history_orphans(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn()
    await f.turn(first)
    fork = await f.fork(first)
    await f.turn(first, continuation=fork)
    campaign_id = f.campaign.id
    await f.session.delete(f.campaign)
    await f.session.commit()
    assert (
        await f.session.scalar(
            text("SELECT count(*) FROM turns WHERE campaign_id=:id"), {"id": campaign_id}
        )
    ) == 0
