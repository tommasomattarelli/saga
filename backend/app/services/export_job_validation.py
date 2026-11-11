from collections import defaultdict
from uuid import UUID

from app.schemas.campaign_export import CampaignExport
from app.services.export_integrity import _require, _unique


def validate_jobs(archive: CampaignExport) -> None:
    states = {row.id: row for row in archive.memory_states}
    policies = {row.id: row for row in archive.memory_policies}
    batches = {row.id: row for row in archive.memory_batches}
    checkpoints = {row.id: row for row in archive.global_checkpoints}
    continuations = {row.id: row for row in archive.continuations}
    turns = {row.id: row for row in archive.turns}
    jobs = {row.id: row for row in archive.jobs}
    attempts = {row.id: row for row in archive.job_attempts}
    _unique(
        archive.job_attempts,
        lambda attempt: (attempt.job_id, attempt.attempt_number),
        "job attempt number",
    )
    ordered_members: dict[UUID, list[UUID]] = {}
    for member in archive.batch_turns:
        ordered_members.setdefault(member.batch_id, []).append(member.turn_id)
    for batch_id in ordered_members:
        ordered_members[batch_id] = [
            row.turn_id
            for row in sorted(
                (row for row in archive.batch_turns if row.batch_id == batch_id),
                key=lambda row: row.ordinal,
            )
        ]
    for generation in archive.generations:
        _require(
            generation.policy_id in policies
            and generation.batch_id in batches
            and generation.job_id in jobs
            and generation.attempt_id in attempts,
            "Generation provenance reference is invalid.",
        )
        _require(
            jobs[generation.job_id].policy_id == generation.policy_id
            and jobs[generation.job_id].batch_id == generation.batch_id,
            "Generation job provenance is inconsistent.",
        )
        _require(
            attempts[generation.attempt_id].job_id == generation.job_id,
            "Generation attempt belongs to another job.",
        )
        _require(
            attempts[generation.attempt_id].campaign_id == generation.campaign_id,
            "Generation attempt belongs to another campaign.",
        )
        expected_roles = (
            {"global"}
            if jobs[generation.job_id].kind == "global"
            else {"batch", "summary", "facts"}
        )
        _require(generation.role in expected_roles, "Generation role differs from its job kind.")
    for attempt in archive.job_attempts:
        _require(attempt.job_id in jobs, "Job attempt reference is invalid.")
    for job in archive.jobs:
        _require(
            job.policy_id in policies
            and job.batch_id in batches
            and job.memory_state_id in states,
            "Job provenance reference is invalid.",
        )
        _require(
            job.previous_checkpoint_id is None or job.previous_checkpoint_id in checkpoints,
            "Job checkpoint reference is invalid.",
        )
        if job.kind == "batch":
            _require(job.previous_checkpoint_id is None, "Batch job has a checkpoint predecessor.")
        elif job.previous_checkpoint_id is not None:
            prior = checkpoints[job.previous_checkpoint_id]
            _require(
                prior.policy_id == job.policy_id
                and prior.batch_id == batches[job.batch_id].previous_batch_id,
                "Global job checkpoint predecessor is inconsistent.",
            )
        else:
            _require(
                batches[job.batch_id].previous_batch_id is None,
                "Global job is missing its checkpoint predecessor.",
            )
        _require(
            job.source_turn_ids == ordered_members.get(job.batch_id, []),
            "Job source membership is inconsistent.",
        )
        _require(
            job.source_hash == batches[job.batch_id].manifest_hash,
            "Job source hash is inconsistent.",
        )
        _require(
            batches[job.batch_id].policy_id == job.policy_id
            and states[job.memory_state_id].policy_id == job.policy_id,
            "Job policy provenance is inconsistent.",
        )
        _require(
            job.context_epoch == states[job.memory_state_id].context_epoch,
            "Job context epoch differs from its origin state.",
        )
    attempts_by_job: dict[UUID, list[int]] = defaultdict(list)
    for attempt in archive.job_attempts:
        attempts_by_job[attempt.job_id].append(attempt.attempt_number)
    for job in archive.jobs:
        recorded = attempts_by_job.get(job.id, [])
        _require(
            len(recorded) == job.attempt_count
            and sorted(recorded) == list(range(1, len(recorded) + 1)),
            "Job attempt sequence is inconsistent.",
        )

    campaign = archive.campaign
    _require(
        campaign.memory_policy_id is None or campaign.memory_policy_id in policies,
        "Campaign policy reference is invalid.",
    )
    _require(
        campaign.active_continuation_id is None
        or campaign.active_continuation_id in continuations,
        "Campaign continuation reference is invalid.",
    )
    _require(
        campaign.active_head_turn_id is None or campaign.active_head_turn_id in turns,
        "Campaign head reference is invalid.",
    )
    _require(
        campaign.active_memory_state_id is None or campaign.active_memory_state_id in states,
        "Campaign memory state reference is invalid.",
    )
    if campaign.active_memory_state_id is not None:
        _require(
            states[campaign.active_memory_state_id].context_epoch == campaign.context_epoch
            and states[campaign.active_memory_state_id].policy_id == campaign.memory_policy_id,
            "Campaign active memory state is inconsistent.",
        )
