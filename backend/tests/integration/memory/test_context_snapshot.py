from app.memory.context_snapshot import capture_turn_context
from tests.integration.memory.storage_support import HistoryFixture, set_head


async def test_capture_freezes_empty_narration_action_in_active_raw_history(
    history_fixture: HistoryFixture,
) -> None:
    fixture = history_fixture
    turn = await fixture.turn(narration="")
    await set_head(fixture, turn.id)
    fixture.campaign.world_state = {"meta": {"current_location": "The Keep"}}
    await fixture.session.commit()

    snapshot = await capture_turn_context(fixture.session, fixture.campaign)

    assert snapshot.campaign_id == fixture.campaign.id
    assert snapshot.head_turn_id == turn.id
    assert snapshot.ancestry_turn_ids == (turn.id,)
    assert snapshot.raw_turn_ids == (turn.id,)
    assert [(message.role, message.content) for message in snapshot.history] == [
        ("user", "Action")
    ]
    assert snapshot.scene.world_state["meta"]["current_location"] == "The Keep"
