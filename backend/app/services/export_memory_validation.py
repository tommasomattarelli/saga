from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from app.schemas.campaign_export import CampaignExport
from app.schemas.campaign_export_memory import ExportBatchTurn
from app.services.export_fact_validation import validate_facts
from app.services.export_integrity import _acyclic, _ancestors, _require, _unique


def ordered_members(batch_turns: Sequence[ExportBatchTurn]) -> dict[UUID, list[ExportBatchTurn]]:
    grouped: dict[UUID, list[ExportBatchTurn]] = defaultdict(list)
    for member in batch_turns:
        grouped[member.batch_id].append(member)
    return {
        batch_id: sorted(rows, key=lambda row: row.ordinal) for batch_id, rows in grouped.items()
    }


def validate_memory(archive: CampaignExport) -> None:
    turns = {row.id: row for row in archive.turns}
    policies = {row.id: row for row in archive.memory_policies}
    batches = {row.id: row for row in archive.memory_batches}
    batch_parents = {row.id: row.previous_batch_id for row in archive.memory_batches}
    checkpoints = {row.id: row for row in archive.global_checkpoints}
    generations = {row.id: row for row in archive.generations}
    continuations = {row.id: row for row in archive.continuations}
    _require(len(policies) <= 1, "Campaign has multiple memory policy snapshots.")
    for policy in archive.memory_policies:
        _require(
            policy.payload_hash == policy.payload.policy_hash(),
            "Memory policy hash is inconsistent.",
        )
    _unique(archive.batch_turns, lambda row: (row.batch_id, row.ordinal), "batch turn ordinal")
    _unique(archive.batch_turns, lambda row: (row.batch_id, row.turn_id), "batch turn")
    _unique(
        archive.memory_batches,
        lambda row: (row.policy_id, row.previous_batch_id, row.source_head_turn_id),
        "batch source",
    )
    for member in archive.batch_turns:
        _require(
            member.batch_id in batches and member.turn_id in turns,
            "Batch turn reference is invalid.",
        )
    ordered_turns: dict[UUID, list[UUID]] = {}
    for batch_id, members in ordered_members(archive.batch_turns).items():
        _require(
            [item.ordinal for item in members] == list(range(1, len(members) + 1)),
            "Batch turn ordinals are not contiguous.",
        )
        ordered_turns[batch_id] = [item.turn_id for item in members]
    for batch in archive.memory_batches:
        _require(
            batch.policy_id in policies and batch.source_head_turn_id in turns,
            "Memory batch reference is invalid.",
        )
        _require(
            batch.previous_batch_id is None or batch.previous_batch_id in batches,
            "Previous batch reference is invalid.",
        )
        member_ids = ordered_turns.get(batch.id, [])
        _require(
            bool(member_ids) and member_ids[-1] == batch.source_head_turn_id,
            "Batch source membership is invalid.",
        )
        _require(
            len(member_ids) == policies[batch.policy_id].payload.batch_turns,
            "Batch membership does not match its policy size.",
        )
        if batch.previous_batch_id:
            previous = batches[batch.previous_batch_id]
            _require(
                previous.policy_id == batch.policy_id,
                "Batch predecessor policy is inconsistent.",
            )
            previous_head = previous.source_head_turn_id
            _require(
                turns[ordered_turns[batch.id][0]].parent_turn_id == previous_head,
                "Batch membership is not contiguous with its predecessor.",
            )
        else:
            first_turn = turns[member_ids[0]]
            _require(
                first_turn.parent_turn_id is None, "Root batch does not start at a history root."
            )
        for previous_turn_id, turn_id in zip(member_ids, member_ids[1:], strict=False):
            _require(
                turns[turn_id].parent_turn_id == previous_turn_id,
                "Batch turn membership is not contiguous.",
            )
    _acyclic(batch_parents)

    for state in archive.memory_states:
        _require(state.policy_id in policies, "Memory state policy reference is invalid.")
        _require(
            state.global_checkpoint_id is None or state.global_checkpoint_id in checkpoints,
            "Memory state checkpoint reference is invalid.",
        )
        _require(
            state.last_compacted_batch_id is None or state.last_compacted_batch_id in batches,
            "Memory state batch reference is invalid.",
        )
        if state.last_compacted_batch_id is not None:
            _require(
                batches[state.last_compacted_batch_id].policy_id == state.policy_id,
                "Memory state batch policy is inconsistent.",
            )
            compacted = _ancestors(batch_parents, state.last_compacted_batch_id)
            published = {summary.batch_id for summary in archive.memory_summaries}
            _require(
                all(batch_id in published for batch_id in compacted),
                "Memory state points to an unpublished batch.",
            )
        if state.global_checkpoint_id is not None:
            checkpoint = checkpoints[state.global_checkpoint_id]
            _require(
                checkpoint.policy_id == state.policy_id,
                "Memory state checkpoint policy is inconsistent.",
            )
            _require(
                state.last_compacted_batch_id is not None,
                "Memory state checkpoint has no compacted prefix.",
            )
            prefix = set(_ancestors(batch_parents, state.last_compacted_batch_id))
            _require(
                checkpoint.batch_id in prefix,
                "Memory state checkpoint is outside its compacted prefix.",
            )
    for row in archive.saves:
        _require(
            row.continuation_id is None or row.continuation_id in continuations,
            "Save continuation reference is invalid.",
        )
        _require(
            row.head_turn_id is None or row.head_turn_id in turns,
            "Save turn reference is invalid.",
        )
        _require(
            row.memory_policy_id is None or row.memory_policy_id in policies,
            "Save policy reference is invalid.",
        )
        _require(
            row.global_checkpoint_id is None or row.global_checkpoint_id in checkpoints,
            "Save checkpoint reference is invalid.",
        )
        _require(
            row.last_compacted_batch_id is None or row.last_compacted_batch_id in batches,
            "Save batch reference is invalid.",
        )
        if row.head_turn_id is not None:
            head = turns[row.head_turn_id]
            _require(
                row.turn_number >= head.turn_number,
                "Save cursor is inconsistent with its history head.",
            )
        if row.last_compacted_batch_id is not None:
            _require(
                batches[row.last_compacted_batch_id].policy_id == row.memory_policy_id,
                "Save compacted batch policy is inconsistent.",
            )
        if row.global_checkpoint_id is not None:
            checkpoint = checkpoints[row.global_checkpoint_id]
            _require(
                checkpoint.policy_id == row.memory_policy_id,
                "Save checkpoint policy is inconsistent.",
            )
            _require(
                row.last_compacted_batch_id is not None, "Save checkpoint has no compacted prefix."
            )
            save_prefix = set(_ancestors(batch_parents, row.last_compacted_batch_id))
            _require(
                checkpoint.batch_id in save_prefix,
                "Save checkpoint is outside its compacted prefix.",
            )

    _unique(archive.memory_summaries, lambda row: row.batch_id, "summary batch")
    for summary in archive.memory_summaries:
        _require(
            summary.policy_id in policies
            and summary.batch_id in batches
            and summary.generation_id in generations,
            "Memory summary reference is invalid.",
        )
        _require(
            batches[summary.batch_id].policy_id == summary.policy_id
            and generations[summary.generation_id].role in {"summary", "batch"}
            and generations[summary.generation_id].batch_id == summary.batch_id
            and generations[summary.generation_id].policy_id == summary.policy_id,
            "Memory summary provenance is inconsistent.",
        )
    _unique(
        archive.global_checkpoints,
        lambda row: (row.policy_id, row.previous_checkpoint_id, row.batch_id),
        "checkpoint transition",
    )
    for checkpoint in archive.global_checkpoints:
        _require(
            checkpoint.policy_id in policies
            and checkpoint.batch_id in batches
            and checkpoint.generation_id in generations,
            "Checkpoint reference is invalid.",
        )
        _require(
            checkpoint.previous_checkpoint_id is None
            or checkpoint.previous_checkpoint_id in checkpoints,
            "Checkpoint predecessor reference is invalid.",
        )
        _require(
            batches[checkpoint.batch_id].policy_id == checkpoint.policy_id
            and generations[checkpoint.generation_id].role == "global"
            and generations[checkpoint.generation_id].batch_id == checkpoint.batch_id
            and generations[checkpoint.generation_id].policy_id == checkpoint.policy_id,
            "Checkpoint provenance is inconsistent.",
        )
        batch = batches[checkpoint.batch_id]
        expected_previous = batch.previous_batch_id
        if checkpoint.previous_checkpoint_id is None:
            _require(expected_previous is None, "Checkpoint chain skips its predecessor batch.")
        else:
            prior = checkpoints[checkpoint.previous_checkpoint_id]
            _require(
                prior.policy_id == checkpoint.policy_id and prior.batch_id == expected_previous,
                "Checkpoint chain is inconsistent with batch history.",
            )

    validate_facts(archive, ordered_turns)
