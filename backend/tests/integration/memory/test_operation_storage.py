from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.memory.operation_contracts import OperationPayload
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation
from tests.integration.memory.storage_support import HistoryFixture


def operation(turn: Turn, ordinal: int = 1) -> TurnOperation:
    return TurnOperation(
        id=uuid4(),
        campaign_id=turn.campaign_id,
        turn_id=turn.id,
        ordinal=ordinal,
        step=0,
        beat=None,
        payload=OperationPayload.model_validate_json(
            '{"origin":"tool","name":"move_to","outcome":"rejected",'
            '"arguments":{"location":"Nowhere"},'
            '"result":{"kind":"error","reason":"domain_rejection",'
            '"description":"No route."},"deltas":[]}'
        ),
    )


async def recorded_turn(f: HistoryFixture, count: int) -> Turn:
    turn = Turn(
        id=uuid4(),
        campaign_id=f.campaign.id,
        turn_number=1,
        player_action="Walk",
        narration="",
        model_used="test",
        operations_version=1,
        operation_count=count,
    )
    f.session.add(turn)
    await f.session.flush()
    return turn


async def test_operations_and_empty_recordings_round_trip(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    first = await recorded_turn(f, 1)
    item = operation(first)
    f.session.add(item)
    empty = await recorded_turn(f, 0)
    legacy = await f.turn()
    await f.session.commit()
    empty_id, legacy_id = empty.id, legacy.id
    f.session.expunge_all()
    stored = await f.session.scalar(select(TurnOperation))
    assert stored is not None
    assert stored.payload.outcome == "rejected"
    assert await f.session.scalar(select(Turn.operation_count).where(Turn.id == empty_id)) == 0
    assert (
        await f.session.scalar(select(Turn.operations_version).where(Turn.id == legacy_id)) is None
    )


@pytest.mark.parametrize("case", ["missing", "gap", "duplicate", "cross_campaign", "unrecorded"])
async def test_invalid_operation_memberships_fail_at_commit(
    history_fixture: HistoryFixture,
    case: str,
) -> None:
    f = history_fixture
    turn = await recorded_turn(f, 1)
    item = operation(turn, 2 if case == "gap" else 1)
    if case == "cross_campaign":
        item.campaign_id = uuid4()
    if case == "unrecorded":
        turn.operations_version = None
        turn.operation_count = None
    if case != "missing":
        f.session.add(item)
    if case == "duplicate":
        f.session.add(operation(turn))
    with pytest.raises(IntegrityError):
        await f.session.commit()
    await f.session.rollback()


async def test_committed_operations_cannot_change_or_be_backfilled(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turn = await recorded_turn(f, 1)
    item = operation(turn)
    f.session.add(item)
    await f.session.commit()
    legacy_id = (await f.turn()).id
    with pytest.raises(IntegrityError):
        await f.session.execute(text("UPDATE turn_operations SET ordinal=2"))
    await f.session.rollback()
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE turns SET operations_version=1, operation_count=0 WHERE id=:id"),
            {"id": legacy_id},
        )
    await f.session.rollback()
