from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.dm import DMPromptContext, DMPromptState, campaign_prompt_context
from app.memory.global_render import render_global_sections
from app.memory.history import history_path
from app.memory.job_coverage import load_coverage
from app.memory.production_policy import MemoryProductionPolicy
from app.memory.recall import RecallSnapshot, snapshot_recall_query
from app.memory.world_state import migrate_world_state
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.quest import QuestRegistry


@dataclass(frozen=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class TurnContextSnapshot:
    campaign_id: UUID
    head_turn_id: UUID | None
    context_epoch: int
    scene: DMPromptState
    prompt: DMPromptContext
    difficulty: str
    history: tuple[HistoryMessage, ...]
    policy: MemoryProductionPolicy | None
    global_checkpoint_id: UUID | None
    intermediate_batch_ids: tuple[UUID, ...]
    recall_snapshot: RecallSnapshot | None
    ancestry_turn_ids: tuple[UUID, ...]
    raw_turn_ids: tuple[UUID, ...]


async def capture_turn_context(db: AsyncSession, campaign: Campaign) -> TurnContextSnapshot:
    turns = await history_path(db, campaign.id, campaign.active_head_turn_id)
    ancestry_ids = tuple(turn.id for turn in turns)
    state = None
    policy = None
    raw_ids = ancestry_ids
    intermediate_ids: tuple[UUID, ...] = ()
    global_summary = ""
    if campaign.active_memory_state_id is not None:
        state = await db.scalar(
            select(MemoryState).where(
                MemoryState.id == campaign.active_memory_state_id,
                MemoryState.campaign_id == campaign.id,
            )
        )
    if state is not None or campaign.memory_policy_id is not None:
        policy_id = state.policy_id if state is not None else campaign.memory_policy_id
        assert policy_id is not None
        if state is not None and (
            state.context_epoch != campaign.context_epoch
            or campaign.memory_policy_id != state.policy_id
        ):
            raise ValueError("The active memory state does not match the campaign context.")
        stored_policy = await db.get(MemoryPolicy, policy_id)
        if stored_policy is None:
            raise ValueError("The active memory policy is missing.")
        policy = stored_policy.payload
        if state is not None:
            coverage = await load_coverage(db, campaign, state, policy)
            raw_ids = coverage.raw_turn_ids
            intermediate_ids = tuple(
                batch.id for batch in coverage.batches[coverage.global_batches :]
            )
        if state is not None and state.global_checkpoint_id is not None:
            checkpoint = await db.get(MemoryGlobalCheckpoint, state.global_checkpoint_id)
            if checkpoint is None:
                raise ValueError("The active memory checkpoint is missing.")
            global_summary = render_global_sections(checkpoint.payload)

    summaries: dict[UUID, str] = {}
    if intermediate_ids:
        rows = await db.execute(
            select(MemorySummary.batch_id, MemorySummary.payload).where(
                MemorySummary.campaign_id == campaign.id,
                MemorySummary.batch_id.in_(intermediate_ids),
            )
        )
        summaries = {batch_id: payload.text for batch_id, payload in rows}
        if set(summaries) != set(intermediate_ids):
            raise ValueError("An active intermediate memory summary is missing.")
    ordered_summaries = [
        summaries[batch_id] for batch_id in intermediate_ids if batch_id in summaries
    ]
    raw_set = set(raw_ids)
    history: list[HistoryMessage] = []
    for turn in turns:
        if turn.id not in raw_set:
            continue
        history.append(HistoryMessage("user", turn.player_action))
        if turn.narration:
            history.append(HistoryMessage("assistant", turn.narration))
    summary_text = "\n".join(ordered_summaries)
    prompt = campaign_prompt_context(campaign, summary_text, global_summary)
    recall_snapshot = await snapshot_recall_query(db, campaign.id)
    scene = DMPromptState(
        world_state=copy.deepcopy(migrate_world_state(campaign.world_state or {})),
        character_data=copy.deepcopy(campaign.character_data or {}),
        world_baseline=copy.deepcopy(campaign.world_baseline or {}),
        quests=QuestRegistry.model_validate(copy.deepcopy(campaign.quests or {})),
    )
    return TurnContextSnapshot(
        campaign_id=campaign.id,
        head_turn_id=campaign.active_head_turn_id,
        context_epoch=campaign.context_epoch,
        scene=scene,
        prompt=prompt,
        difficulty=str(campaign.difficulty),
        history=tuple(history),
        policy=policy,
        global_checkpoint_id=state.global_checkpoint_id if state is not None else None,
        intermediate_batch_ids=intermediate_ids,
        recall_snapshot=recall_snapshot,
        ancestry_turn_ids=ancestry_ids,
        raw_turn_ids=raw_ids,
    )
