from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.campaign_export import CampaignExport, ExportCampaign, ExportTurn
from app.schemas.campaign_export_memory import ExportJob, ExportMemoryFact


def empty_archive() -> CampaignExport:
    now = datetime.now(UTC)
    campaign = ExportCampaign(
        id=uuid4(),
        world_slug="starter",
        world_version=None,
        name="Test",
        language="en",
        status="active",
        difficulty="medium",
        turn_number=0,
        memory_policy_id=None,
        active_continuation_id=None,
        active_head_turn_id=None,
        active_memory_state_id=None,
        context_epoch=0,
        fork_on_next_action=False,
        character_data={},
        world_baseline=None,
        world_state={},
        quests={},
        global_summary=None,
        persona_preset=None,
        persona_xml=None,
        created_at=now,
        updated_at=now,
    )
    return CampaignExport(
        format_version=1,
        exported_at=now,
        campaign=campaign,
        turns=[],
        turn_operations=[],
        continuations=[],
        saves=[],
        memory_policies=[],
        memory_states=[],
        memory_batches=[],
        batch_turns=[],
        memory_summaries=[],
        global_checkpoints=[],
        memory_facts=[],
        fact_sources=[],
        generations=[],
        jobs=[],
        job_attempts=[],
    )


def test_campaign_export_has_versioned_archive_envelope() -> None:
    assert empty_archive().format_version == 1


def test_archive_rejects_unknown_claims_and_future_versions() -> None:
    archive = empty_archive().model_dump(mode="python")
    archive["format_version"] = 2
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)
    archive["format_version"] = True
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)
    archive["format_version"] = 1
    campaign = archive["campaign"]
    campaign["unknown_claim"] = "value"
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)


@pytest.mark.parametrize("version", [1.0, "1"])
def test_archive_version_is_a_strict_integer(version: object) -> None:
    archive = empty_archive().model_dump(mode="python")
    archive["format_version"] = version
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)


def test_archive_requires_an_explicit_format_version() -> None:
    archive = empty_archive().model_dump(mode="python")
    del archive["format_version"]
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)


def test_job_excludes_private_claim_material() -> None:
    now = datetime.now(UTC)
    fields = {
        "id": uuid4(),
        "campaign_id": uuid4(),
        "policy_id": uuid4(),
        "batch_id": uuid4(),
        "memory_state_id": uuid4(),
        "context_epoch": 0,
        "kind": "batch",
        "previous_checkpoint_id": None,
        "source_turn_ids": [uuid4()],
        "source_hash": "a" * 64,
        "instruction_version": "v1",
        "language": "en",
        "manifest_hash": "b" * 64,
        "producer_version": "v1",
        "prompt_version": "v1",
        "state": "queued",
        "attempt_count": 0,
        "retry_cycle": 0,
        "cycle_attempt_count": 0,
        "last_error": None,
        "activation_state": "pending",
        "created_at": now,
        "updated_at": now,
    }
    assert ExportJob.model_validate(fields).source_turn_ids
    for excluded in ("claim_token", "lease_expires_at", "instruction_text"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ExportJob.model_validate({**fields, excluded: "secret"})


def test_persisted_counters_are_strict_and_nonnegative() -> None:
    archive = empty_archive().model_dump(mode="python")
    archive["campaign"]["turn_number"] = True
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)
    archive["campaign"]["turn_number"] = -1
    with pytest.raises(ValidationError):
        CampaignExport.model_validate(archive)


def test_legacy_fact_null_provenance_is_preserved_and_categories_are_closed() -> None:
    now = datetime.now(UTC)
    fact = {
        "id": uuid4(),
        "campaign_id": uuid4(),
        "turn_number": 1,
        "entity_name": "Mira",
        "entity_type": "npc",
        "content": "Mira guards the gate.",
        "batch_id": None,
        "policy_id": None,
        "ordinal": None,
        "category": None,
        "assertion_type": None,
        "fact_metadata": None,
        "generation_id": None,
        "schema_version": None,
        "created_at": now,
        "updated_at": now,
    }
    assert ExportMemoryFact.model_validate(fact).schema_version is None
    fact["category"] = "made_up"
    with pytest.raises(ValidationError):
        ExportMemoryFact.model_validate(fact)


def test_turn_json_columns_accept_json_values_but_not_python_objects() -> None:
    fields = {
        "id": uuid4(),
        "campaign_id": uuid4(),
        "turn_number": 1,
        "continuation_id": None,
        "parent_turn_id": None,
        "history_depth": None,
        "parent_depth": None,
        "operations_version": None,
        "operation_count": None,
        "player_action": "Look around",
        "narration": "The room is quiet.",
        "narration_segments": [{"text": "The room is quiet."}],
        "dice_rolls": None,
        "companion_actions": None,
        "world_updates": {"clock": 1},
        "scene_mood": None,
        "suggested_actions": None,
        "model_used": "model",
        "importance_score": 5,
        "summary": None,
        "summarization_failed": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    assert ExportTurn.model_validate(fields).world_updates == {"clock": 1}
    fields["world_updates"] = {"bad": object()}
    with pytest.raises(ValidationError):
        ExportTurn.model_validate(fields)
