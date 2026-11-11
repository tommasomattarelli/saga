import pytest

from app.schemas.campaign_export import CampaignExport
from app.services.export_validation import ExportIntegrityError, validate_campaign_export


def assert_archive_rejects_corruption(source: CampaignExport) -> None:
    changed_policy = source.model_copy(deep=True)
    policy = changed_policy.memory_policies[0]
    policy.payload = policy.payload.model_copy(
        update={"batch_turns": policy.payload.batch_turns + 1}
    )
    policy.payload_hash = policy.payload.policy_hash()
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(changed_policy)

    missing_summary = source.model_copy(deep=True)
    missing_summary.memory_summaries = []
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(missing_summary)

    missing_sources = source.model_copy(deep=True)
    missing_sources.fact_sources = []
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(missing_sources)

    wrong_source = source.model_copy(deep=True)
    head = wrong_source.campaign.active_head_turn_id
    assert head is not None
    wrong_source.fact_sources[0].turn_id = head
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_source)

    wrong_global = source.model_copy(deep=True)
    checkpoint = wrong_global.global_checkpoints[0]
    generation = next(
        row
        for row in wrong_global.generations
        if row.batch_id == checkpoint.batch_id and row.role == "summary"
    )
    generation.role = "batch"
    checkpoint.generation_id = generation.id
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_global)

    wrong_epoch = source.model_copy(deep=True)
    wrong_epoch.campaign.context_epoch += 1
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_epoch)

    detached_prefix = source.model_copy(deep=True)
    save = min(detached_prefix.saves, key=lambda row: row.turn_number)
    save.last_compacted_batch_id = detached_prefix.memory_batches[-1].id
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(detached_prefix)

    wrong_hash = source.model_copy(deep=True)
    wrong_hash.memory_policies[0].payload_hash = "0" * 64
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_hash)

    wrong_attempt_count = source.model_copy(deep=True)
    wrong_attempt_count.jobs[0].attempt_count = 10**12
    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(wrong_attempt_count)
