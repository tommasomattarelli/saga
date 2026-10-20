"""ADR 0018 B — ensure/status/retry/recovery lifecycle on real PostgreSQL."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.exceptions import ValidationError
from app.memory.embedding_lifecycle import (
    ensure_campaign_embedding_index,
    recover_interrupted_rebuilds,
    retry_campaign_embedding_index,
)
from app.memory.embedding_status import campaign_embedding_status
from app.models.campaign import Campaign, Difficulty
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.source_embedding import SourceEmbedding
from tests.integration.embedding_support import (
    add_turn,
    create_user_campaign,
    fake_space,
    install_provider,
)


async def _index_count(db, campaign_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign_id)
        )
    ).scalar_one()


async def _source_count(db, index_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(SourceEmbedding)
            .where(SourceEmbedding.index_id == index_id)
        )
    ).scalar_one()


def _manual_index(campaign: Campaign, **overrides) -> EmbeddingIndex:
    space = fake_space()
    values = {
        "campaign_id": campaign.id,
        "provider": space.provider,
        "model": space.model,
        "endpoint_name": space.endpoint_name,
        "endpoint_identity": space.endpoint_identity,
        "pipeline_version": space.pipeline_version,
        "dimension": None,
        "is_active": False,
        "rebuild_state": State.QUEUED,
    }
    values.update(overrides)
    return EmbeddingIndex(**values)


async def test_ensure_is_idempotent_and_starts_only_the_requested_campaign(
    db_session, monkeypatch
) -> None:
    install_provider(monkeypatch)
    user, first = await create_user_campaign(db_session)
    second = Campaign(user_id=user.id, world_slug="w", name="other", difficulty=Difficulty.EASY)
    db_session.add(second)
    await db_session.commit()

    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=first.id)
    again = await ensure_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=first.id
    )

    assert again["target"] is not None
    assert await _index_count(db_session, first.id) == 1
    assert await _index_count(db_session, second.id) == 0


async def test_status_is_side_effect_free(db_session, monkeypatch) -> None:
    provider = install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    before = await _index_count(db_session, campaign.id)
    first = await campaign_embedding_status(db_session, user_id=user.id, campaign_id=campaign.id)
    second = await campaign_embedding_status(db_session, user_id=user.id, campaign_id=campaign.id)

    assert first == second
    assert await _index_count(db_session, campaign.id) == before
    assert provider.calls["embed"] == 0


async def test_missing_credential_creates_no_job_and_reports_a_reason(
    db_session, monkeypatch
) -> None:
    async def refuse(user_id, *, space=None):
        raise ValidationError("Add a personal key for `openrouter` in settings.")

    install_provider(monkeypatch, resolve=refuse)
    user, campaign = await create_user_campaign(db_session)

    status = await ensure_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )

    assert await _index_count(db_session, campaign.id) == 0
    assert status["active"] is None and status["target"] is None
    assert status["suspended_reason"] is not None


async def test_missing_credential_stops_an_existing_target_with_a_reason(
    db_session, monkeypatch
) -> None:
    async def refuse(user_id, *, space=None):
        raise ValidationError("Add a personal key for `openrouter` in settings.")

    install_provider(monkeypatch, resolve=refuse)
    user, campaign = await create_user_campaign(db_session)
    index = _manual_index(campaign, rebuild_state=State.QUEUED)
    db_session.add(index)
    await db_session.commit()

    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    refreshed = (
        await db_session.execute(select(EmbeddingIndex).where(EmbeddingIndex.id == index.id))
    ).scalar_one()
    assert refreshed.rebuild_state is State.FAILED
    assert refreshed.last_error and "personal key" in refreshed.last_error


@pytest.mark.parametrize("terminal", [State.FAILED, State.CANCELLED])
async def test_terminal_job_is_not_restarted_by_ensure_but_retry_resumes_it(
    db_session, monkeypatch, terminal: State
) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    index = _manual_index(campaign, rebuild_state=terminal, last_error="boom")
    db_session.add(index)
    await db_session.commit()

    status = await ensure_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )
    assert status["needs_retry"] is True
    assert await _index_count(db_session, campaign.id) == 1

    retried = await retry_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )
    assert retried["target"] is not None
    assert retried["target"]["id"] == index.id
    assert await _index_count(db_session, campaign.id) == 1


@pytest.mark.parametrize("terminal", [State.FAILED, State.CANCELLED])
async def test_terminal_target_blocks_a_new_job_even_with_an_active_index(
    db_session, monkeypatch, terminal: State
) -> None:
    """The normal case: an older index A stays active while target B failed or was
    cancelled. Reopening the campaign must not silently recreate B."""
    provider = install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    active = _manual_index(
        campaign,
        model="old-model",
        endpoint_identity="https://old.test/v1",
        is_active=True,
        rebuild_state=State.COMPLETED,
        dimension=8,
    )
    terminal_index = _manual_index(campaign, rebuild_state=terminal, last_error="boom")
    db_session.add_all([active, terminal_index])
    await db_session.commit()

    first = await ensure_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )
    second = await ensure_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )

    assert await _index_count(db_session, campaign.id) == 2
    assert provider.calls["embed"] == 0
    assert first["needs_retry"] is True
    assert second["needs_retry"] is True

    retried = await retry_campaign_embedding_index(
        db_session, user_id=user.id, campaign_id=campaign.id
    )
    assert retried["target"] is not None
    assert retried["target"]["id"] == terminal_index.id
    assert await _index_count(db_session, campaign.id) == 2


async def test_restart_reconciles_missing_sources_without_ensure(db_session, monkeypatch) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "The bridge is out.")
    index = _manual_index(campaign, rebuild_state=State.QUEUED)
    db_session.add(index)
    await db_session.commit()

    await recover_interrupted_rebuilds()

    assert await _source_count(db_session, index.id) == 1
