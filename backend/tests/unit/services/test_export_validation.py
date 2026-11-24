from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.campaign_export import CampaignExport, ExportCampaign, ExportTurn
from app.schemas.campaign_export_history import ExportContinuation
from app.schemas.campaign_export_memory import ExportJob, ExportMemoryBatch, ExportMemoryFact
from app.services.export_validation import ExportIntegrityError, validate_campaign_export


def empty_archive() -> CampaignExport:
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
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    return CampaignExport(
        format_version=1,
        exported_at=datetime.now(UTC),
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


def test_empty_archive_is_referentially_valid() -> None:
    validate_campaign_export(empty_archive())


def test_rejects_cross_campaign_turn_reference_with_safe_error() -> None:
    archive = empty_archive()
    archive.turns.append(
        ExportTurn(
            id=uuid4(),
            campaign_id=uuid4(),
            turn_number=1,
            continuation_id=None,
            parent_turn_id=None,
            history_depth=None,
            parent_depth=None,
            operations_version=None,
            operation_count=None,
            player_action="act",
            narration="result",
            narration_segments=None,
            dice_rolls=None,
            companion_actions=None,
            world_updates=None,
            scene_mood=None,
            suggested_actions=None,
            model_used="model",
            importance_score=1,
            summary=None,
            summarization_failed=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )

    with pytest.raises(ExportIntegrityError, match="campaign") as error:
        validate_campaign_export(archive)
    assert "backend" not in str(error.value)
    assert "traceback" not in str(error.value)


def test_rejects_duplicate_turn_ids() -> None:
    archive = empty_archive()
    turn = ExportTurn(
        id=uuid4(),
        campaign_id=archive.campaign.id,
        turn_number=1,
        continuation_id=None,
        parent_turn_id=None,
        history_depth=None,
        parent_depth=None,
        operations_version=None,
        operation_count=None,
        player_action="act",
        narration="result",
        narration_segments=None,
        dice_rolls=None,
        companion_actions=None,
        world_updates=None,
        scene_mood=None,
        suggested_actions=None,
        model_used="model",
        importance_score=1,
        summary=None,
        summarization_failed=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    archive.turns.extend([turn, turn.model_copy()])

    with pytest.raises(ExportIntegrityError):
        validate_campaign_export(archive)


def test_accepts_turn_parent_across_forked_continuations() -> None:
    archive = empty_archive()
    now = datetime.now(UTC)
    root_continuation_id = uuid4()
    fork_continuation_id = uuid4()
    root_turn_id = uuid4()
    archive.continuations.extend(
        [
            ExportContinuation(
                id=root_continuation_id,
                campaign_id=archive.campaign.id,
                parent_continuation_id=None,
                fork_head_turn_id=None,
                created_at=now,
                updated_at=now,
            ),
            ExportContinuation(
                id=fork_continuation_id,
                campaign_id=archive.campaign.id,
                parent_continuation_id=root_continuation_id,
                fork_head_turn_id=root_turn_id,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    archive.turns.extend(
        [
            _turn(archive.campaign.id, root_turn_id, root_continuation_id, None, 1),
            _turn(archive.campaign.id, uuid4(), fork_continuation_id, root_turn_id, 2),
        ]
    )

    validate_campaign_export(archive)


def test_rejects_parent_cycle() -> None:
    archive = empty_archive()
    first_id, second_id = uuid4(), uuid4()
    archive.turns.extend(
        [
            _turn(archive.campaign.id, first_id, None, second_id, None),
            _turn(archive.campaign.id, second_id, None, first_id, None),
        ]
    )

    with pytest.raises(ExportIntegrityError, match="cycle"):
        validate_campaign_export(archive)


def test_accepts_multiple_legacy_facts_without_production_ordinals() -> None:
    archive = empty_archive()
    now = datetime.now(UTC)
    archive.memory_facts.extend(
        [
            ExportMemoryFact(
                id=uuid4(),
                campaign_id=archive.campaign.id,
                turn_number=1,
                entity_name="Mira",
                entity_type="npc",
                content="A legacy fact.",
                batch_id=None,
                policy_id=None,
                ordinal=None,
                category=None,
                assertion_type=None,
                fact_metadata=None,
                generation_id=None,
                schema_version=None,
                created_at=now,
                updated_at=now,
            ),
            ExportMemoryFact(
                id=uuid4(),
                campaign_id=archive.campaign.id,
                turn_number=2,
                entity_name="Rook",
                entity_type="npc",
                content="Another legacy fact.",
                batch_id=None,
                policy_id=None,
                ordinal=None,
                category=None,
                assertion_type=None,
                fact_metadata=None,
                generation_id=None,
                schema_version=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )

    validate_campaign_export(archive)


def test_rejects_batch_with_missing_policy_reference() -> None:
    archive = empty_archive()
    now = datetime.now(UTC)
    archive.memory_batches.append(
        ExportMemoryBatch(
            id=uuid4(),
            campaign_id=archive.campaign.id,
            policy_id=uuid4(),
            previous_batch_id=None,
            source_head_turn_id=uuid4(),
            manifest_hash="a" * 64,
            created_at=now,
            updated_at=now,
        )
    )

    with pytest.raises(ExportIntegrityError, match="batch reference"):
        validate_campaign_export(archive)


def test_job_schema_rejects_opaque_claim_fields() -> None:
    with pytest.raises(ValidationError):
        ExportJob.model_validate({"claim_token": str(uuid4())})


def _turn(
    campaign_id: UUID,
    turn_id: UUID,
    continuation_id: UUID | None,
    parent_turn_id: UUID | None,
    depth: int | None,
) -> ExportTurn:
    now = datetime.now(UTC)
    return ExportTurn(
        id=turn_id,
        campaign_id=campaign_id,
        turn_number=depth or 1,
        continuation_id=continuation_id,
        parent_turn_id=parent_turn_id,
        history_depth=depth,
        parent_depth=depth - 1 if depth is not None else None,
        operations_version=None,
        operation_count=None,
        player_action="act",
        narration="result",
        narration_segments=None,
        dice_rolls=None,
        companion_actions=None,
        world_updates=None,
        scene_mood=None,
        suggested_actions=None,
        model_used="model",
        importance_score=1,
        summary=None,
        summarization_failed=False,
        created_at=now,
        updated_at=now,
    )
