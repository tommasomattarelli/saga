from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.user import User
from app.schemas.campaign_export import CampaignExport, ExportCampaign
from app.security.auth import get_current_user
from app.services.campaign_export import CampaignExportNotFoundError
from app.services.export_validation import ExportIntegrityError


@pytest.fixture
def export_user():
    user = User(
        id=uuid4(), username="export-test", email="export@example.test", hashed_password="unused"
    )

    async def override_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


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


def export_campaign_validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as error:
        ExportCampaign.model_validate({})
    return error.value


def test_export_delegates_campaign_and_owner_ids(mocker, export_user: User) -> None:
    campaign_id = uuid4()
    archive = empty_archive()
    build = mocker.patch(
        "app.api.export.build_campaign_export", autospec=True, return_value=archive
    )

    response = TestClient(app).get(f"/api/export/{campaign_id}")

    assert response.status_code == 200
    assert response.json()["format_version"] == 1
    build.assert_awaited_once_with(campaign_id, export_user.id)


def test_export_maps_not_found_to_404(mocker, export_user: User) -> None:
    mocker.patch(
        "app.api.export.build_campaign_export",
        autospec=True,
        side_effect=CampaignExportNotFoundError("private detail"),
    )

    response = TestClient(app).get(f"/api/export/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Campaign not found"
    assert "private detail" not in response.text


@pytest.mark.parametrize(
    "error",
    [
        ExportIntegrityError("secret integrity detail"),
        export_campaign_validation_error(),
    ],
)
def test_export_sanitizes_inconsistent_archives(
    mocker, export_user: User, error: Exception
) -> None:
    mocker.patch("app.api.export.build_campaign_export", autospec=True, side_effect=error)

    response = TestClient(app).get(f"/api/export/{uuid4()}")

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "code": "campaign_export_inconsistent",
        "message": "Campaign export could not be validated.",
    }
    assert "secret" not in response.text
