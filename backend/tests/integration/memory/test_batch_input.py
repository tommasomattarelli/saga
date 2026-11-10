import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.memory.batch_input import load_batch_input
from app.memory.history import HistoryIntegrityError
from app.models.turn_operation import TurnOperation
from tests.integration.memory.batch_input_support import (
    op,
    payload,
    projection_operations,
    recorded_turn,
)
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


async def test_loads_mixed_legacy_and_recorded_sources_in_batch_ordinal_order(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    legacy = await f.turn(number=90, narration="Legacy prose")
    first = await recorded_turn(
        f,
        parent=legacy,
        number=3,
        action="Open the gate",
        narration="The captain says, “The gate is yours.”",
        operations=[
            op(
                1,
                payload(
                    "invoke_npc",
                    {"name": "Captain", "context": "The gate"},
                    result={
                        "kind": "npc",
                        "description": "The captain answers.",
                        "npc_id": "captain",
                        "status": "speaking",
                        "lines": ["The gate is yours."],
                    },
                ),
            )
        ],
    )
    item = await batch(f, [legacy, first])

    source = await load_batch_input(f.session, f.campaign.id, item.id)

    assert [turn.reference for turn in source.turns] == ["t1", "t2"]
    assert [turn.turn_id for turn in source.turns] == [legacy.id, first.id]
    assert [turn.player_action for turn in source.turns] == ["Action", "Open the gate"]
    assert [turn.narration for turn in source.turns] == [
        "Legacy prose",
        "The captain says, “The gate is yours.”",
    ]
    assert source.turns[0].operations is None
    assert source.turns[1].operations is not None
    assert len(source.turns[1].operations) == 1
    assert source.turns[1].operations[0].payload.result.kind == "npc"
    assert source.canonical_json().count("The gate is yours.") == 1


async def test_empty_narration_and_recorded_empty_operations_are_preserved(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    first = await recorded_turn(f, parent=None, number=8, action="Wait", narration="")
    second = await recorded_turn(
        f, parent=first, number=8, action="Listen", narration="A bell rings."
    )
    item = await batch(f, [first, second])

    source = await load_batch_input(f.session, f.campaign.id, item.id)

    assert source.turns[0].narration == ""
    assert source.turns[0].operations == ()
    assert source.turns[1].operations == ()


async def test_projection_filters_only_routine_operations_and_preserves_ordinals(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    full = projection_operations()
    turn = await recorded_turn(
        f, parent=None, number=1, action="Travel", narration="They set out.", operations=full
    )
    second = await recorded_turn(
        f, parent=turn, number=1, action="Continue", narration="They continue."
    )
    item = await batch(f, [turn, second])

    source = await load_batch_input(f.session, f.campaign.id, item.id)

    assert [operation.ordinal for operation in source.turns[0].operations or ()] == [
        3,
        4,
        5,
        7,
        8,
    ]
    assert [operation.payload.name for operation in source.turns[0].operations or ()] == [
        "request_dice",
        "move_to",
        "invoke_npc",
        "advance_time",
        "move_to",
    ]
    assert [operation.ordinal for operation in full] == list(range(1, 10))
    stored = list(
        (
            await f.session.scalars(
                select(TurnOperation)
                .where(TurnOperation.turn_id == turn.id)
                .order_by(TurnOperation.ordinal)
            )
        ).all()
    )
    assert [operation.ordinal for operation in stored] == list(range(1, 10))


async def test_canonical_source_and_hash_are_stable_between_loads(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turn = await recorded_turn(
        f, parent=None, number=1, action="Look around", narration="A quiet room."
    )
    second_turn = await recorded_turn(
        f, parent=turn, number=1, action="Leave", narration="They leave."
    )
    item = await batch(f, [turn, second_turn])

    first = await load_batch_input(f.session, f.campaign.id, item.id)
    second = await load_batch_input(f.session, f.campaign.id, item.id)

    assert first.canonical_json() == second.canonical_json()
    assert first.source_hash() == second.source_hash()
    assert first.source_hash() == hashlib.sha256(first.canonical_json().encode()).hexdigest()
    assert json.loads(first.canonical_json())["turns"][0]["turn_id"] == str(turn.id)


async def test_load_rejects_batch_from_another_campaign(history_fixture: HistoryFixture) -> None:
    f = history_fixture
    turn = await recorded_turn(f, parent=None, number=1, action="Wait", narration="Time passes.")
    second_turn = await recorded_turn(
        f, parent=turn, number=1, action="Continue", narration="Still waiting."
    )
    item = await batch(f, [turn, second_turn])

    with pytest.raises(HistoryIntegrityError):
        await load_batch_input(f.session, uuid4(), item.id)
