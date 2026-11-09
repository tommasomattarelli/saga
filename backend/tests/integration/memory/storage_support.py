from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.production_policy import MemoryProductionPolicy
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.turn import Turn


def production_policy(batch_turns: int = 2) -> MemoryProductionPolicy:
    return MemoryProductionPolicy.model_validate_json(
        """{"raw_turns":2,"batch_turns":BATCH_SIZE,"intermediate_limit":1,"backlog_batches":0,
        "facts":{"max_per_batch":4,"importance_levels":[
            {"name":"ordinary","criteria":"Significant event","examples":"A clue"},
            {"name":"critical","criteria":"Campaign consequence","examples":"A death"}]},
        "global":{"target_words":400},"jobs":{"max_attempts":2,
        "retry_backoff_seconds":[1],"request_timeout_seconds":10,"lease_seconds":30,
        "poll_seconds":1},"admission":{"wait_timeout_seconds":5}}""".replace(
            "BATCH_SIZE", str(batch_turns)
        )
    )


@dataclass
class HistoryFixture:
    session: AsyncSession
    campaign: Campaign
    policy: MemoryPolicy
    root: HistoryContinuation

    async def turn(
        self,
        parent: Turn | None = None,
        *,
        continuation: HistoryContinuation | None = None,
        number: int = 1,
        narration: str = "Narration",
    ) -> Turn:
        turn = Turn(
            id=uuid4(),
            campaign_id=self.campaign.id,
            continuation_id=(continuation or self.root).id,
            parent_turn_id=parent.id if parent else None,
            history_depth=(parent.history_depth + 1) if parent and parent.history_depth else 1,
            turn_number=number,
            player_action="Action",
            narration=narration,
            model_used="test",
        )
        self.session.add(turn)
        await self.session.commit()
        return turn

    async def fork(self, head: Turn | None) -> HistoryContinuation:
        continuation = HistoryContinuation(
            id=uuid4(),
            campaign_id=self.campaign.id,
            parent_continuation_id=head.continuation_id if head else self.root.id,
            fork_head_turn_id=head.id if head else None,
        )
        self.session.add(continuation)
        await self.session.commit()
        return continuation


@pytest.fixture
async def history_fixture(db_session: AsyncSession, test_user: dict) -> HistoryFixture:
    campaign = Campaign(
        id=uuid4(),
        user_id=test_user["user"].id,
        world_slug="test",
        name="History",
        difficulty=Difficulty.MEDIUM,
    )
    db_session.add(campaign)
    await db_session.flush()
    payload = production_policy()
    policy = MemoryPolicy(
        id=uuid4(),
        campaign_id=campaign.id,
        schema_version=1,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(id=uuid4(), campaign_id=campaign.id)
    db_session.add_all([policy, root])
    await db_session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await db_session.commit()
    return HistoryFixture(db_session, campaign, policy, root)


async def set_head(fixture: HistoryFixture, head_id: UUID | None) -> None:
    fixture.campaign.active_head_turn_id = head_id
    await fixture.session.commit()
