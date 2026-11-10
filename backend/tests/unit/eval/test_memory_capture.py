from uuid import uuid4

import pytest
from eval.memory_capture import (
    CapturedMemorySource,
    LegacyTurn,
    ordered_turns,
    partition_capture,
)

from app.memory.batch_source_contracts import BatchTurnSource


def test_ordered_turns_reject_duplicate_display_numbers() -> None:
    rows = [
        LegacyTurn(id=uuid4(), turn_number=1, player_action="A", narration=""),
        LegacyTurn(id=uuid4(), turn_number=1, player_action="B", narration=""),
    ]
    with pytest.raises(ValueError, match="duplicate display turn numbers"):
        ordered_turns(tuple(rows))


def test_ordered_turns_reject_duplicate_ids() -> None:
    turn_id = uuid4()
    rows = tuple(
        LegacyTurn(id=turn_id, turn_number=number, player_action="A", narration="")
        for number in (1, 2)
    )
    with pytest.raises(ValueError, match="duplicate turn identities"):
        ordered_turns(rows)


def test_capture_source_preserves_empty_narration_and_null_operations() -> None:
    turn = BatchTurnSource(
        reference="t1", turn_id=uuid4(), player_action="Wait", narration="", operations=None
    )
    source = CapturedMemorySource(campaign_id=uuid4(), language="en", turns=(turn,))

    encoded = source.canonical_json()
    assert '"narration":""' in encoded
    assert '"operations":null' in encoded
    assert source.model_dump(mode="json")["turns"][0]["operations"] is None


def test_canonical_json_is_stable() -> None:
    campaign_id = uuid4()
    source = CapturedMemorySource(
        campaign_id=campaign_id,
        language="it",
        turns=(
            BatchTurnSource(
                reference="t1",
                turn_id=uuid4(),
                player_action="Ciao",
                narration="Salve",
                operations=None,
            ),
        ),
    )
    assert source.canonical_json() == source.canonical_json()
    assert str(campaign_id) in source.canonical_json()


def test_partition_rebases_complete_batches_and_retains_tail_and_empty_narration() -> None:
    turns = tuple(
        BatchTurnSource(
            reference=f"t{index}",
            turn_id=uuid4(),
            player_action=f"Action {index}",
            narration="" if index == 3 else f"Narration {index}",
            operations=None,
        )
        for index in range(1, 4)
    )
    source = CapturedMemorySource(campaign_id=uuid4(), language="en", turns=turns)

    batches, tail = partition_capture(source, 2)

    assert [[turn.reference for turn in batch.turns] for batch in batches] == [["t1", "t2"]]
    assert [turn.reference for turn in tail] == ["t1"]
    assert tail[0].narration == ""
    assert tail[0].turn_id == turns[2].turn_id
