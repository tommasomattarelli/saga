from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import CTE

from app.models.turn import Turn


class HistoryIntegrityError(ValueError):
    pass


def history_ancestry(campaign_id: UUID, head_turn_id: UUID) -> CTE:
    ancestry = (
        select(Turn.id, Turn.parent_turn_id)
        .where(
            Turn.id == head_turn_id,
            Turn.campaign_id == campaign_id,
            Turn.continuation_id.is_not(None),
        )
        .cte("ancestry", recursive=True)
    )
    ancestry = ancestry.union_all(
        select(Turn.id, Turn.parent_turn_id)
        .join(ancestry, Turn.id == ancestry.c.parent_turn_id)
        .where(Turn.campaign_id == campaign_id)
    )
    return ancestry


async def history_path(
    session: AsyncSession, campaign_id: UUID, head_turn_id: UUID | None
) -> list[Turn]:
    if head_turn_id is None:
        return []
    ancestry = history_ancestry(campaign_id, head_turn_id)
    turns = list(
        (
            await session.scalars(
                select(Turn).join(ancestry, Turn.id == ancestry.c.id).order_by(Turn.history_depth)
            )
        ).all()
    )
    if not turns:
        raise HistoryIntegrityError("The selected history does not belong to this campaign.")
    return turns
