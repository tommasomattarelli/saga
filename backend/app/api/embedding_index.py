"""Authenticated campaign embedding-index lifecycle endpoints (ADR 0018 B)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.exceptions import NotFoundError
from app.memory import embedding_lifecycle as lifecycle
from app.memory.embedding_status import IndexStatus, campaign_embedding_status
from app.models.user import User
from app.schemas.embedding_index import EmbeddingIndexStatus
from app.security.auth import get_current_user

router = APIRouter()


@router.post("/{campaign_id}/embedding-index/ensure", response_model=EmbeddingIndexStatus)
async def ensure_index(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IndexStatus:
    return await _guard(
        lifecycle.ensure_campaign_embedding_index(db, user_id=user.id, campaign_id=campaign_id)
    )


@router.get("/{campaign_id}/embedding-index", response_model=EmbeddingIndexStatus)
async def get_index_status(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IndexStatus:
    return await _guard(campaign_embedding_status(db, user_id=user.id, campaign_id=campaign_id))


@router.post("/{campaign_id}/embedding-index/retry", response_model=EmbeddingIndexStatus)
async def retry_index(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IndexStatus:
    return await _guard(
        lifecycle.retry_campaign_embedding_index(db, user_id=user.id, campaign_id=campaign_id)
    )


@router.post("/{campaign_id}/embedding-index/cancel", response_model=EmbeddingIndexStatus)
async def cancel_index(
    campaign_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IndexStatus:
    return await _guard(
        lifecycle.cancel_campaign_embedding_index(db, user_id=user.id, campaign_id=campaign_id)
    )


async def _guard(coro: Awaitable[IndexStatus]) -> IndexStatus:
    try:
        return await coro
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
