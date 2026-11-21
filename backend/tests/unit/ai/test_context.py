import uuid
from dataclasses import replace

import pytest

from app.ai.context import build_context
from app.ai.prompts.dm import DMPromptContext, DMPromptState
from app.memory.context_snapshot import HistoryMessage, TurnContextSnapshot
from app.models.quest import QuestRegistry


def snapshot(history: tuple[HistoryMessage, ...] = ()) -> TurnContextSnapshot:
    return TurnContextSnapshot(
        campaign_id=uuid.uuid4(),
        head_turn_id=None,
        context_epoch=0,
        scene=DMPromptState({}, {"name": "Mira"}, {}, QuestRegistry()),
        prompt=DMPromptContext(),
        difficulty="easy",
        history=history,
        policy=None,
        global_checkpoint_id=None,
        intermediate_batch_ids=(),
        recall_snapshot=None,
        ancestry_turn_ids=(),
        raw_turn_ids=(),
    )


@pytest.mark.asyncio
async def test_build_context_uses_frozen_snapshot_without_campaign_reads(mocker):
    turn_context = snapshot(
        (HistoryMessage("user", "Earlier action"), HistoryMessage("assistant", "Earlier answer"))
    )
    turn_context = replace(
        turn_context,
        prompt=DMPromptContext(
            language="en", summary_context="Batch memory", global_summary="Global"
        ),
    )
    db = mocker.Mock()
    db.execute = mocker.AsyncMock(
        side_effect=AssertionError("snapshot path queried campaign/history")
    )
    mocker.patch("app.ai.context.search_similar_facts", mocker.AsyncMock(return_value=[]))

    context = await build_context(turn_context, "Current action", db)

    assert [message["content"] for message in context.messages] == [
        "Earlier action",
        "Earlier answer",
        "Current action",
    ]
    assert "Batch memory" in context.system_prompt
    assert "Global" in context.system_prompt


@pytest.mark.asyncio
async def test_build_context_preserves_all_history_without_token_truncation(mocker):
    turn_context = snapshot(
        (HistoryMessage("user", "x" * 5000), HistoryMessage("assistant", "y" * 5000))
    )
    mocker.patch("app.ai.context.search_similar_facts", mocker.AsyncMock(return_value=[]))

    context = await build_context(turn_context, "current", mocker.Mock())

    assert [message["content"] for message in context.messages] == [
        "x" * 5000,
        "y" * 5000,
        "current",
    ]
