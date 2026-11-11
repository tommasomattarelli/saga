from collections import defaultdict
from uuid import UUID

from app.schemas.campaign_export import CampaignExport, ExportContinuation, ExportTurn
from app.services.export_integrity import _acyclic, _ancestors, _require, _unique


def head_in_history(
    head_id: UUID | None,
    continuation_id: UUID | None,
    turns: dict[UUID, ExportTurn],
    continuations: dict[UUID, ExportContinuation],
) -> bool:
    if head_id is None:
        return True
    if head_id not in turns or continuation_id not in continuations:
        return False
    assert continuation_id is not None
    if turns[head_id].continuation_id == continuation_id:
        return True
    fork_head = continuations[continuation_id].fork_head_turn_id
    return head_id in _ancestors(
        {turn.id: turn.parent_turn_id for turn in turns.values()}, fork_head
    )


def validate_history(archive: CampaignExport) -> None:
    campaign_id = archive.campaign.id
    turns = {row.id: row for row in archive.turns}
    continuations = {row.id: row for row in archive.continuations}
    _acyclic({row.id: row.parent_turn_id for row in archive.turns})
    _acyclic({row.id: row.parent_continuation_id for row in archive.continuations})
    _unique(archive.turn_operations, lambda row: row.id, "turn operation")
    _unique(archive.turn_operations, lambda row: (row.turn_id, row.ordinal), "operation ordinal")
    ordinals: dict[UUID, list[int]] = defaultdict(list)
    for op in archive.turn_operations:
        _require(
            op.campaign_id == campaign_id and op.turn_id in turns,
            "Turn operation reference is invalid.",
        )
        ordinals[op.turn_id].append(op.ordinal)
    _unique(
        [turn for turn in archive.turns if turn.continuation_id is not None],
        lambda turn: (turn.continuation_id, turn.parent_turn_id),
        "continuation parent turn",
    )
    for cont in archive.continuations:
        if cont.parent_continuation_id is None:
            _require(cont.fork_head_turn_id is None, "Root continuation has a fork head.")
        else:
            _require(
                head_in_history(
                    cont.fork_head_turn_id, cont.parent_continuation_id, turns, continuations
                ),
                "Continuation fork head is outside its parent history.",
            )
    _require(
        sum(cont.parent_continuation_id is None for cont in archive.continuations) <= 1,
        "Campaign has multiple root continuations.",
    )
    for turn in archive.turns:
        recorded = ordinals.get(turn.id, [])
        if turn.operations_version is None:
            _require(
                turn.operation_count is None and not recorded,
                "Legacy turn contains versioned operations.",
            )
        else:
            _require(
                len(recorded) == turn.operation_count, "Turn operation count is inconsistent."
            )
            _require(
                sorted(recorded) == list(range(1, len(recorded) + 1)),
                "Turn operation ordinals are invalid.",
            )
        if turn.continuation_id is None:
            _require(
                turn.parent_turn_id is None
                and turn.history_depth is None
                and turn.parent_depth is None,
                "Legacy turn history is inconsistent.",
            )
            continue
        _require(turn.continuation_id in continuations, "Turn continuation reference is invalid.")
        continuation = continuations[turn.continuation_id]
        if turn.parent_turn_id is None:
            _require(
                turn.history_depth == 1
                and turn.parent_depth == 0
                and continuation.fork_head_turn_id is None,
                "Turn root depth or fork is inconsistent.",
            )
            continue
        parent = turns[turn.parent_turn_id]
        _require(
            turn.history_depth is not None
            and parent.history_depth is not None
            and turn.history_depth == parent.history_depth + 1
            and turn.parent_depth == parent.history_depth,
            "Turn history depth is inconsistent.",
        )
        if turn.continuation_id != parent.continuation_id:
            _require(
                continuation.parent_continuation_id is not None
                and continuation.fork_head_turn_id == parent.id
                and head_in_history(
                    parent.id, continuation.parent_continuation_id, turns, continuations
                ),
                "Turn fork ancestry is inconsistent.",
            )
