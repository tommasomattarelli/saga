from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.memory.job_claims import lock_campaign, retry_job
from app.memory.job_lifecycle import wake_memory_worker
from app.memory.job_scheduler import coordinate_memory
from app.models.memory_job import MemoryJob
from app.models.user import User
from app.security.auth import get_current_user
from app.services.action_errors import context_changed

router = APIRouter()


class MemoryRetry(BaseModel):
    model_config = {"extra": "forbid"}

    expected_head_turn_id: UUID | None
    expected_context_epoch: int = Field(ge=0)


class MemoryRetryResponse(BaseModel):
    retried: int


@router.post("/{campaign_id}/memory/retry", response_model=MemoryRetryResponse)
async def retry_memory(
    campaign_id: UUID,
    body: MemoryRetry,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryRetryResponse:
    campaign = await lock_campaign(db, campaign_id)
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if (
        campaign.active_head_turn_id != body.expected_head_turn_id
        or campaign.context_epoch != body.expected_context_epoch
    ):
        error = context_changed()
        raise HTTPException(status_code=error.status_code, detail=error.detail)
    ids = await coordinate_memory(db, campaign_id)
    failed = list(
        await db.scalars(
            select(MemoryJob.id).where(
                MemoryJob.id.in_(ids),
                MemoryJob.state.in_(("blocked", "exhausted")),
            )
        )
    )
    retried = 0
    for job_id in failed:
        retried += await retry_job(db, campaign_id, job_id)
    await db.commit()
    wake_memory_worker()
    return MemoryRetryResponse(retried=retried)
