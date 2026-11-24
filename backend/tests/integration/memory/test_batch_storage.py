from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.memory.batch_compatibility import batch_is_compatible
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture


async def batch(
    f: HistoryFixture, turns: list[Turn], previous: MemoryBatch | None = None
) -> MemoryBatch:
    result = MemoryBatch(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        previous_batch_id=previous.id if previous else None,
        source_head_turn_id=turns[-1].id,
        manifest_hash="a" * 64,
    )
    f.session.add(result)
    await f.session.flush()
    f.session.add_all(
        [
            MemoryBatchTurn(
                campaign_id=f.campaign.id, batch_id=result.id, ordinal=i, turn_id=turn.id
            )
            for i, turn in enumerate(turns, start=1)
        ]
    )
    await f.session.commit()
    return result


async def test_full_producer_membership_controls_compatibility(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await f.turn(number=1)
    second = await f.turn(first, number=4)
    third = await f.turn(second, number=4)
    fourth = await f.turn(third, number=9)
    prefix = await batch(f, [first, second])
    crossing = await batch(f, [third, fourth], prefix)
    fork = await f.fork(third)
    new_future = await f.turn(third, continuation=fork, number=9)
    assert await batch_is_compatible(f.session, f.campaign.id, prefix.id, new_future.id)
    assert not await batch_is_compatible(f.session, f.campaign.id, crossing.id, new_future.id)
    assert not await batch_is_compatible(f.session, f.campaign.id, crossing.id, third.id)
    assert not await batch_is_compatible(f.session, uuid4(), prefix.id, second.id)
    alternative = await batch(f, [third, new_future], prefix)
    assert await batch_is_compatible(f.session, f.campaign.id, alternative.id, new_future.id)


@pytest.mark.parametrize("case", ["short", "reversed", "gap", "not_root"])
async def test_invalid_partitions_fail_at_commit(
    history_fixture: HistoryFixture, case: str
) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    third = await f.turn(second)
    sources = {
        "short": [first],
        "reversed": [second, first],
        "gap": [first, third],
        "not_root": [second, third],
    }
    with pytest.raises(IntegrityError):
        await batch(f, sources[case])
    await f.session.rollback()


async def test_membership_cannot_change_after_commit(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("DELETE FROM memory_batch_turns WHERE batch_id=:id"), {"id": item.id}
        )
        await f.session.commit()
    await f.session.rollback()
