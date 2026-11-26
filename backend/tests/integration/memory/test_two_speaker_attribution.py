import json
from typing import cast
from uuid import uuid4

from eval.attribution.manifest import load_scenarios
from sqlalchemy import func, select

from app.memory.batch_source_contracts import BatchInput
from app.memory.job_publication import publish_job
from app.memory.operation_contracts import RecordedOperation
from app.models.campaign import Campaign, Difficulty
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_document import MemorySummary
from app.models.memory_fact import MemoryFact
from tests.integration.memory.batch_input_support import payload, recorded_turn
from tests.integration.memory.job_support import outputs_for
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_publication import _claimed_job

REAL_BATCH = "real_batch_anonymized"


def _facts_payload(npc_name: str, source_turn: str) -> str:
    return json.dumps(
        {
            "facts": [
                {
                    "content": (
                        f"The player told {npc_name} that Kestrel the ferryman swore the sealed "
                        "charter lay under the third stair of the shrine, wrapped in green wax."
                    ),
                    "category": "information",
                    "assertion_type": "statement",
                    "entities": [
                        {
                            "name": "the player",
                            "type": "player",
                            "role": "speaker reporting the claim",
                        },
                        {
                            "name": "Kestrel",
                            "type": "npc",
                            "role": "original source named in the report",
                        },
                        {"name": npc_name, "type": "npc", "role": "listener"},
                    ],
                    "attribution": [0],
                    "source_turns": [source_turn],
                    "temporal_references": [],
                    "importance": {
                        "level": "ordinary",
                        "reason": "An attributed report of a clue.",
                    },
                },
                {
                    "content": f"{npc_name} agreed to look for the charter beneath the third stair.",
                    "category": "commitment",
                    "assertion_type": "intention",
                    "entities": [
                        {"name": npc_name, "type": "npc", "role": "speaker making the commitment"}
                    ],
                    "attribution": [0],
                    "source_turns": [source_turn],
                    "temporal_references": [],
                    "importance": {"level": "ordinary", "reason": "A commitment with a location."},
                },
            ]
        }
    )


def _npc_id(source: BatchInput, npc_name: str) -> str:
    for turn in source.turns:
        for operation in turn.operations or ():
            if (
                operation.payload.name == "invoke_npc"
                and operation.payload.arguments.get("name") == npc_name
            ):
                return str(operation.payload.result.npc_id)
    raise AssertionError(f"No invoke_npc operation for {npc_name}")


async def _published_facts(
    f: HistoryFixture, source: BatchInput, npc_name: str, source_turn: str
) -> list[MemoryFact]:
    turns = []
    parent = None
    for index, source_turn_source in enumerate(source.turns, start=1):
        operations: list[RecordedOperation] = []
        for source_op in source_turn_source.operations or ():
            result = source_op.payload.result.model_dump(mode="json")
            if result["kind"] == "npc":
                result = {
                    "kind": "npc",
                    "description": "The NPC responds.",
                    "npc_id": result["npc_id"],
                    "status": result["status"],
                    "lines": [],
                    "action": result["action"],
                    "axis_changes": result["axis_changes"],
                }
            operations.append(
                RecordedOperation(
                    id=source_op.id,
                    ordinal=source_op.ordinal,
                    step=source_op.step,
                    beat=source_op.beat,
                    payload=payload(
                        source_op.payload.name,
                        cast(dict[str, object], source_op.payload.arguments),
                        deltas=[
                            delta.model_dump(mode="json") for delta in source_op.payload.deltas
                        ],
                        result=result,
                    ),
                )
            )
        turns.append(
            await recorded_turn(
                f,
                parent=parent,
                number=index,
                action=source_turn_source.player_action,
                narration=source_turn_source.narration,
                operations=operations,
                turn_id=source_turn_source.turn_id,
            )
        )
        parent = turns[-1]

    _, claim, generations, item, _ = await _claimed_job(
        f,
        turns=tuple(turns),
        manifest_hash=source.source_hash(),
        raw_by_role={
            "summary": json.dumps(
                {
                    "text": (
                        f"The player reported a clue about the charter; {npc_name} agreed to look."
                    )
                }
            ),
            "facts": _facts_payload(npc_name, source_turn),
        },
    )
    assert await publish_job(f.session, claim, outputs_for(generations))
    await f.session.commit()
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemorySummary)
            .where(MemorySummary.batch_id == item.id)
        )
        == 1
    )
    return list(
        await f.session.scalars(
            select(MemoryFact).where(MemoryFact.batch_id == item.id).order_by(MemoryFact.ordinal)
        )
    )


def _assert_separate_speakers(facts: list[MemoryFact], npc_name: str, npc_id: str) -> None:
    assert [fact.ordinal for fact in facts] == [1, 2]
    player_fact, npc_fact = facts
    assert player_fact.assertion_type == "statement"
    assert player_fact.category == "information"
    assert player_fact.fact_metadata.attribution == (0,)
    player_speaker = player_fact.fact_metadata.entities[0]
    assert (player_speaker.name, player_speaker.type) == ("the player", "player")
    assert player_speaker.canonical_ref is None
    assert any(
        entity.name == "Kestrel" and entity.canonical_ref is None
        for entity in player_fact.fact_metadata.entities
    )
    assert npc_fact.assertion_type == "intention"
    assert npc_fact.fact_metadata.attribution == (0,)
    npc_speaker = npc_fact.fact_metadata.entities[0]
    assert npc_speaker.name == npc_name
    assert npc_speaker.canonical_ref is not None
    assert str(npc_speaker.canonical_ref.id) == npc_id


async def test_synthetic_two_speaker_batch_publishes_two_facts(
    history_fixture: HistoryFixture,
) -> None:
    npc_name, npc_id = "Vela", "30000000-0000-4000-8000-000000000009"
    source = BatchInput.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "turns": [
                    {
                        "reference": "t1",
                        "turn_id": "10000000-0000-4000-8000-000000000011",
                        "player_action": (
                            "I tell Vela that Kestrel swore the sealed charter lies under the "
                            "third stair, wrapped in green wax. I ask her to look."
                        ),
                        "narration": 'Vela: "I will look for the charter beneath the third stair."',
                        "operations": [
                            {
                                "id": "20000000-0000-4000-8000-000000000011",
                                "ordinal": 1,
                                "step": None,
                                "beat": None,
                                "payload": {
                                    "origin": "npc",
                                    "name": "invoke_npc",
                                    "outcome": "succeeded",
                                    "arguments": {"name": npc_name, "context": "The player asks."},
                                    "result": {
                                        "kind": "npc",
                                        "npc_id": npc_id,
                                        "status": "speaking",
                                        "action": None,
                                        "axis_changes": {},
                                    },
                                    "deltas": [],
                                },
                            }
                        ],
                    },
                    {
                        "reference": "t2",
                        "turn_id": "10000000-0000-4000-8000-000000000012",
                        "player_action": "I wait for dawn.",
                        "narration": "Nothing changes.",
                        "operations": [],
                    },
                ],
            }
        )
    )
    facts = await _published_facts(history_fixture, source, npc_name, "t1")
    _assert_separate_speakers(facts, npc_name, npc_id)


async def _batch_size_fixture(f: HistoryFixture, turns: int) -> HistoryFixture:
    payload = f.policy.payload.model_copy(update={"batch_turns": turns})
    campaign = Campaign(
        id=uuid4(),
        user_id=f.campaign.user_id,
        world_slug="test",
        name="Attribution batch",
        difficulty=Difficulty.MEDIUM,
    )
    policy = MemoryPolicy(
        id=uuid4(),
        campaign_id=campaign.id,
        schema_version=f.policy.schema_version,
        payload=payload,
        payload_hash=payload.policy_hash(),
    )
    root = HistoryContinuation(id=uuid4(), campaign_id=campaign.id)
    f.session.add_all([campaign, policy, root])
    await f.session.flush()
    campaign.memory_policy_id = policy.id
    campaign.active_continuation_id = root.id
    await f.session.flush()
    return HistoryFixture(f.session, campaign, policy, root)


async def test_anonymized_real_batch_publishes_two_facts(history_fixture: HistoryFixture) -> None:
    scenario = next(s for s in load_scenarios() if s.name == REAL_BATCH)
    fixture = await _batch_size_fixture(history_fixture, len(scenario.source.turns))
    npc_name = "Vela"
    facts = await _published_facts(fixture, scenario.source, npc_name, "t3")
    _assert_separate_speakers(facts, npc_name, _npc_id(scenario.source, npc_name))
