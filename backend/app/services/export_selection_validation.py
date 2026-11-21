from uuid import UUID

from app.schemas.campaign_export import CampaignExport
from app.services.export_history_validation import head_in_history
from app.services.export_integrity import _ancestors, _require


def validate_selections(archive: CampaignExport) -> None:
    turns = {row.id: row for row in archive.turns}
    continuations = {row.id: row for row in archive.continuations}
    policies = {row.id: row for row in archive.memory_policies}
    states = {row.id: row for row in archive.memory_states}
    batches = {row.id: row for row in archive.memory_batches}
    checkpoints = {row.id: row for row in archive.global_checkpoints}
    turn_parents = {row.id: row.parent_turn_id for row in archive.turns}
    batch_parents = {row.id: row.previous_batch_id for row in archive.memory_batches}
    summaries = {row.batch_id for row in archive.memory_summaries}

    def validate(
        head_id: UUID | None,
        continuation_id: UUID | None,
        policy_id: UUID | None,
        last_batch_id: UUID | None,
        checkpoint_id: UUID | None,
    ) -> None:
        if policy_id is None:
            _require(
                all(
                    value is None
                    for value in (head_id, continuation_id, last_batch_id, checkpoint_id)
                ),
                "Legacy history has partial memory references.",
            )
            return
        _require(
            policy_id in policies and continuation_id in continuations,
            "Selected history contract is incomplete.",
        )
        _require(
            head_in_history(head_id, continuation_id, turns, continuations),
            "Selected head is outside its continuation history.",
        )
        ancestry = set(_ancestors(turn_parents, head_id))
        prefix = _ancestors(batch_parents, last_batch_id)
        policy = policies[policy_id].payload
        maximum = max(len(ancestry) - policy.raw_turns, 0) // policy.batch_turns
        _require(len(prefix) <= maximum, "Selected memory coverage consumes protected raw turns.")
        for batch_id in prefix:
            _require(
                batches[batch_id].policy_id == policy_id
                and batches[batch_id].source_head_turn_id in ancestry
                and batch_id in summaries,
                "Selected memory batch is unpublished or outside its history.",
            )
        if checkpoint_id is not None:
            _require(checkpoint_id in checkpoints, "Selected checkpoint reference is invalid.")
            checkpoint = checkpoints[checkpoint_id]
            _require(
                checkpoint.policy_id == policy_id and checkpoint.batch_id in prefix,
                "Selected checkpoint is outside its compacted prefix.",
            )
            global_count = len(_ancestors(batch_parents, checkpoint.batch_id))
            _require(
                global_count <= max(maximum - policy.intermediate_limit, 0),
                "Selected global coverage consumes protected intermediate batches.",
            )

    campaign = archive.campaign
    if campaign.memory_policy_id is None:
        _require(
            campaign.active_memory_state_id is None, "Legacy campaign has an active memory state."
        )
        validate(campaign.active_head_turn_id, campaign.active_continuation_id, None, None, None)
    else:
        _require(
            campaign.active_memory_state_id in states, "Campaign active memory state is missing."
        )
        assert campaign.active_memory_state_id is not None
        state = states[campaign.active_memory_state_id]
        validate(
            campaign.active_head_turn_id,
            campaign.active_continuation_id,
            campaign.memory_policy_id,
            state.last_compacted_batch_id,
            state.global_checkpoint_id,
        )
    if campaign.active_head_turn_id is not None:
        _require(
            campaign.turn_number >= turns[campaign.active_head_turn_id].turn_number,
            "Campaign turn label precedes its completed head.",
        )
    for save in archive.saves:
        validate(
            save.head_turn_id,
            save.continuation_id,
            save.memory_policy_id,
            save.last_compacted_batch_id,
            save.global_checkpoint_id,
        )
