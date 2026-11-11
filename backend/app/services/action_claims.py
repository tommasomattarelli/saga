import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.core.action_policy import get_action_policy
from app.memory.context_snapshot import TurnContextSnapshot, capture_turn_context
from app.memory.job_claims import lock_campaign
from app.memory.job_lifecycle import wake_memory_worker
from app.models.campaign import Campaign, CampaignStatus
from app.models.history import HistoryContinuation
from app.models.turn import Turn
from app.models.turn_request import TurnRequest
from app.schemas.campaign import TurnResponse, TurnSubmit
from app.services.action_admission import check_action_capacity
from app.services.action_errors import ActionError, context_changed


@dataclass(frozen=True)
class ActionClaim:
    campaign_id: UUID
    request_id: UUID
    execution_token: UUID
    starting_head_turn_id: UUID | None
    context_epoch: int
    continuation_id: UUID
    history_depth: int
    turn_number: int
    context: TurnContextSnapshot


def _payload_hash(body: TurnSubmit) -> str:
    payload = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def recover_action_slot(db: AsyncSession, campaign: Campaign) -> None:
    request = await db.scalar(
        select(TurnRequest)
        .where(
            TurnRequest.campaign_id == campaign.id,
            TurnRequest.state == "running",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if request is None:
        return
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    if (
        request.execution_expires_at is not None and request.execution_expires_at <= now
    ) or request.context_epoch != campaign.context_epoch:
        request.state = "interrupted"
        request.execution_token = None
        request.execution_expires_at = None
        request.error = "The action was interrupted; submit a new action to continue."
        campaign.active_action_request_id = None
        await db.flush()


def _existing_result(
    request: TurnRequest,
    campaign: Campaign,
    body: TurnSubmit,
) -> TurnResponse:
    if request.payload_hash != _payload_hash(body):
        raise ActionError(
            "action_payload_conflict", "This request ID was already used for another payload."
        )
    if request.state == "committed":
        if (
            request.context_epoch != campaign.context_epoch
            or request.result_turn_id != campaign.active_head_turn_id
        ):
            raise context_changed(request.result_turn_id)
        if request.response_payload is None:
            raise ActionError(
                "action_result_unavailable", "The stored action response is unavailable."
            )
        return TurnResponse.model_validate(request.response_payload)
    if request.state == "invalidated":
        raise context_changed()
    if request.state == "interrupted":
        raise ActionError(
            "action_interrupted",
            request.error or "The action was interrupted; submit a new action.",
        )
    raise ActionError("action_in_progress", "This action is already in progress.")


async def _try_claim(
    db: AsyncSession,
    campaign_id: UUID,
    owner_id: UUID,
    body: TurnSubmit,
) -> tuple[ActionClaim | TurnResponse | None, float, float, ActionError | None]:
    campaign = await lock_campaign(db, campaign_id)
    if campaign is None or campaign.user_id != owner_id:
        raise ActionError("campaign_not_found", "Campaign not found", status_code=404)
    existing = await db.get(TurnRequest, body.request_id, populate_existing=True)
    if existing is not None and existing.campaign_id != campaign_id:
        raise ActionError("action_payload_conflict", "This request ID is unavailable.")
    await recover_action_slot(db, campaign)
    if existing is not None:
        return _existing_result(existing, campaign, body), 0, 0, None
    if campaign.status != CampaignStatus.ACTIVE:
        raise ActionError("campaign_inactive", "Campaign is not active", status_code=400)
    if (
        campaign.context_epoch != body.expected_context_epoch
        or campaign.active_head_turn_id != body.expected_head_turn_id
    ):
        raise context_changed()
    if campaign.active_action_request_id is not None:
        raise ActionError("action_in_progress", "Another action is already in progress.")
    policy, blocked = await check_action_capacity(db, campaign)
    if blocked is not None:
        return None, policy.admission.wait_timeout_seconds, policy.jobs.poll_seconds, blocked
    context = await capture_turn_context(db, campaign)
    if campaign.fork_on_next_action:
        continuation = HistoryContinuation(
            id=uuid4(),
            campaign_id=campaign.id,
            parent_continuation_id=campaign.active_continuation_id,
            fork_head_turn_id=campaign.active_head_turn_id,
        )
        db.add(continuation)
        await db.flush()
        campaign.active_continuation_id = continuation.id
        campaign.fork_on_next_action = False
    assert campaign.active_continuation_id is not None
    parent = (
        await db.get(Turn, campaign.active_head_turn_id) if campaign.active_head_turn_id else None
    )
    depth = (parent.history_depth or 0) + 1 if parent else 1
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    token = uuid4()
    campaign.turn_number += 1
    campaign.active_action_request_id = body.request_id
    db.add(
        TurnRequest(
            request_id=body.request_id,
            campaign_id=campaign.id,
            payload_hash=_payload_hash(body),
            starting_head_turn_id=campaign.active_head_turn_id,
            context_epoch=campaign.context_epoch,
            state="running",
            execution_token=token,
            execution_expires_at=now
            + timedelta(seconds=get_action_policy().execution_lease_seconds),
            claimed_turn_number=campaign.turn_number,
        )
    )
    return (
        ActionClaim(
            campaign.id,
            body.request_id,
            token,
            campaign.active_head_turn_id,
            campaign.context_epoch,
            campaign.active_continuation_id,
            depth,
            campaign.turn_number,
            context,
        ),
        0,
        0,
        None,
    )


async def claim_action(
    campaign_id: UUID, owner_id: UUID, body: TurnSubmit
) -> ActionClaim | TurnResponse:
    started = monotonic()
    while True:
        async with dependencies.async_session() as db:
            try:
                result, timeout, interval, blocked = await _try_claim(
                    db, campaign_id, owner_id, body
                )
            except ActionError:
                await db.commit()
                raise
            await db.commit()
        wake_memory_worker()
        if result is not None:
            return result
        assert blocked is not None
        remaining = timeout - (monotonic() - started)
        if blocked.code != "memory_busy" or remaining <= 0:
            raise blocked
        await asyncio.sleep(min(interval, remaining))


async def interrupt_action(claim: ActionClaim, message: str) -> None:
    async with dependencies.async_session() as db:
        campaign = await lock_campaign(db, claim.campaign_id)
        request = await db.get(TurnRequest, claim.request_id, populate_existing=True)
        if (
            campaign is not None
            and request is not None
            and request.state == "running"
            and request.execution_token == claim.execution_token
        ):
            request.state, request.error = "interrupted", message
            request.execution_token = request.execution_expires_at = None
            if campaign.active_action_request_id == claim.request_id:
                campaign.active_action_request_id = None
            await db.commit()


async def load_action_claim(db: AsyncSession, claim: ActionClaim) -> tuple[Campaign, TurnRequest]:
    campaign = await lock_campaign(db, claim.campaign_id)
    request = await db.get(TurnRequest, claim.request_id, populate_existing=True)
    now = await db.scalar(select(func.clock_timestamp()))
    assert isinstance(now, datetime)
    if (
        campaign is None
        or request is None
        or request.state != "running"
        or request.execution_token != claim.execution_token
        or request.execution_expires_at is None
        or request.execution_expires_at <= now
        or campaign.active_action_request_id != claim.request_id
        or campaign.context_epoch != claim.context_epoch
        or campaign.active_head_turn_id != claim.starting_head_turn_id
    ):
        raise context_changed()
    return campaign, request
