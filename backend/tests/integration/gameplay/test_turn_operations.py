"""ADR 0020 §6: operation outcomes survive the real turn path."""

import json
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from app.ai.providers.schemas import ToolCall
from app.models.campaign import Campaign
from app.models.save import Save
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation
from tests.action_support import action_body
from tests.integration.gameplay.test_npc_beats import actor
from tests.integration.gameplay.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)

pytestmark = pytest.mark.asyncio


async def _operations(db_session, campaign_id: str) -> tuple[Turn, list[TurnOperation]]:
    await db_session.commit()
    db_session.expire_all()
    turn = await db_session.scalar(select(Turn).where(Turn.campaign_id == uuid.UUID(campaign_id)))
    assert turn is not None
    rows = list(
        (
            await db_session.scalars(
                select(TurnOperation)
                .where(TurnOperation.turn_id == turn.id)
                .order_by(TurnOperation.ordinal)
            )
        ).all()
    )
    return turn, rows


async def test_quest_ledger(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)

    def tool(ident: str, status: str) -> ToolCall:
        return ToolCall(
            id=ident,
            name="update_quest",
            arguments={"quest_id": "who_am_i", "status": status},
        )

    _script(
        provider,
        [
            _reply("", tool("complete", "completed"), tool("restore", "active")),
            _reply("A clue."),
            _reply("Morning."),
        ],
    )

    result = await _take_turn(auth_client, campaign["id"])
    assert result["quests"]["active"][0]["id"] == "who_am_i"
    turn, rows = await _operations(db_session, campaign["id"])
    assert turn.operations_version == 1 and turn.operation_count == len(rows)
    changes = [r.payload for r in rows if r.payload.name == "update_quest"]
    assert [r.outcome for r in changes] == ["succeeded", "succeeded"]
    assert all(r.deltas for r in changes)
    assert all(change.deltas[0].before != change.deltas[0].after for change in changes)
    assert any(r.payload.origin == "finalization" for r in rows)
    assert "operations" not in result and "operations" not in result["world_state"]


async def test_tool_ledger(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply(
                "",
                ToolCall(id="mood", name="set_scene_mood", arguments={"mood": "tense"}),
                ToolCall(id="bad", name="move_to", arguments={"wrong": "field"}),
                ToolCall(id="route", name="move_to", arguments={"location": "Nowhere"}),
                ToolCall(
                    id="invalid-dice",
                    name="request_dice",
                    arguments={"ability": "strength"},
                ),
                ToolCall(
                    id="valid-dice",
                    name="request_dice",
                    arguments={"stat": "DEX", "check": "Balance", "difficulty": "normal"},
                ),
            ),
            _reply("The scene settles."),
        ],
    )
    result = await _take_turn(auth_client, campaign["id"])
    _, rows = await _operations(db_session, campaign["id"])
    tools = [r.payload for r in rows if r.payload.origin == "tool"]
    assert [r.name for r in tools] == [
        "request_dice",
        "request_dice",
        "set_scene_mood",
        "move_to",
        "move_to",
    ]
    assert tools[0].result.reason == "invalid_arguments" and tools[1].result.kind == "check"
    assert tools[1].outcome == "succeeded"
    assert tools[1].deltas == ()
    assert tools[2].outcome == "succeeded"
    assert [tools[i].result.reason for i in (3, 4)] == ["invalid_arguments", "domain_rejection"]
    assert result["tool_events"] == []
    assert "operations" not in result


async def test_npc_failure_ledger(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = "{}"
    _script(provider, [_reply("", actor("New Farmer")), _reply("The farmer waits.")])

    result = await _take_turn(auth_client, campaign["id"])
    _, rows = await _operations(db_session, campaign["id"])
    npc = [r.payload for r in rows if r.payload.origin == "npc"]
    assert [(r.name, r.outcome) for r in npc] == [
        ("create_npc", "succeeded"),
        ("invoke_npc", "failed"),
    ]
    assert npc[0].result.kind == "npc" and npc[0].deltas
    assert npc[1].result.reason == "npc_failed" and npc[1].deltas == ()
    assert result["narration"].count("The farmer waits.") == 1


async def test_npc_speech_ledger(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = json.dumps(
        {"status": "speaking", "lines": ["The bridge is safe."]}
    )
    _script(
        provider,
        [
            _reply("", ToolCall(id="npc", name="invoke_npc", arguments={"name": "Lyra"})),
            _reply("Lyra speaks. [[npc:Lyra:1]]"),
        ],
    )
    result = await _take_turn(auth_client, campaign["id"])
    _, rows = await _operations(db_session, campaign["id"])
    npc = next(
        r.payload for r in rows if r.payload.origin == "npc" and r.payload.name == "invoke_npc"
    )
    assert npc.outcome == "succeeded" and npc.result.kind == "npc"
    assert npc.result.lines == ["The bridge is safe."]
    assert result["narration"].count("The bridge is safe.") == 1


async def test_operation_rollback(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply(
                "",
                ToolCall(
                    id="complete",
                    name="update_quest",
                    arguments={"quest_id": "who_am_i", "status": "completed"},
                ),
            ),
            _reply("The clue is found."),
            _reply("Morning."),
        ],
    )
    await db_session.commit()
    initial_turns = await db_session.scalar(
        select(Turn.id).where(Turn.campaign_id == uuid.UUID(campaign["id"]))
    )
    initial_quests = campaign["quests"]
    initial_world = campaign["world_state"]

    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if "INSERT INTO turn_operations" in statement:
            raise RuntimeError("injected operation insert failure")

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        response = await auth_client.post(
            f"/api/campaigns/{campaign['id']}/action",
            json=await action_body(auth_client, campaign["id"], "I discover the truth"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    await db_session.rollback()
    assert response.status_code == 500
    assert (
        await db_session.scalar(
            select(Turn.id).where(Turn.campaign_id == uuid.UUID(campaign["id"]))
        )
        == initial_turns
    )
    stored_campaign = await db_session.get(Campaign, uuid.UUID(campaign["id"]))
    assert stored_campaign is not None
    assert stored_campaign.world_state == initial_world
    assert stored_campaign.quests == initial_quests
    assert (
        await db_session.scalar(
            select(Save.id).where(
                Save.campaign_id == uuid.UUID(campaign["id"]), Save.is_auto.is_(True)
            )
        )
        is None
    )


async def test_plain_turn_marker(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    _script(provider, [_reply("Nothing changes."), _reply("Morning.")])
    result = await _take_turn(auth_client, campaign["id"])
    turn, rows = await _operations(db_session, campaign["id"])
    assert turn.operations_version == 1 and turn.operation_count == len(rows)
    assert rows
    assert all(r.payload.origin == "finalization" for r in rows)
    assert "operations" not in json.dumps(result)


async def test_tool_exception_is_sanitized(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply("", ToolCall(id="item", name="add_item", arguments={"name": "Silver Key"})),
            _reply("The attempt fails quietly."),
        ],
    )
    with patch(
        "app.ai.tools.tools_inventory.AddItem.execute",
        side_effect=RuntimeError("/internal/path secret"),
    ):
        result = await _take_turn(auth_client, campaign["id"])
    _, rows = await _operations(db_session, campaign["id"])
    failed = next(r.payload for r in rows if r.payload.name == "add_item")
    assert (failed.outcome, failed.result.reason) == ("failed", "execution_failed")
    serialized = json.dumps(result)
    assert all(secret not in serialized for secret in ("/internal/path", "RuntimeError"))


async def test_round_trip_travel_deltas(auth_client, db_session, generation_clients):
    campaign = await _create_campaign(auth_client)
    initial_position = campaign["world_state"]["player_position"]
    provider = await _openai_provider(auth_client, generation_clients)
    _script(
        provider,
        [
            _reply(
                "",
                ToolCall(id="outbound", name="move_to", arguments={"location": "Thornhaven"}),
                ToolCall(
                    id="return",
                    name="move_to",
                    arguments={"location": "Shrine of First Light"},
                ),
            ),
            _reply("You return to the shrine."),
        ],
    )
    await _take_turn(auth_client, campaign["id"])
    _, rows = await _operations(db_session, campaign["id"])
    moves = [r.payload for r in rows if r.payload.name == "move_to"]
    assert len(moves) == 2 and all(op.outcome == "succeeded" and op.deltas for op in moves)

    assert all(
        all(
            any(d.scope == "world_state" and d.path[0] == key for d in op.deltas)
            for key in ("player_position", "clock")
        )
        for op in moves
    )
    stored_campaign = await db_session.get(Campaign, uuid.UUID(campaign["id"]))
    assert stored_campaign is not None
    assert stored_campaign.world_state["player_position"] == initial_position
