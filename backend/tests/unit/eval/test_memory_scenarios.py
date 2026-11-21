import json
from pathlib import Path

import pytest
from eval.memory_scenarios.build import batch_plan, build_scenario, write_scenario

from app.memory.batch_source_contracts import BatchInput


def test_batch_plan_reports_explicit_requirement_without_choosing_a_matrix() -> None:
    plan = batch_plan(
        raw_turns=8,
        intermediate_limit=2,
        global_updates=3,
        batch_size=4,
        available_turns=37,
        resolution_turn=34,
    )
    assert plan["required_turns"] == 28
    assert plan["sufficient"] is True
    assert plan["global_prefix_turns"] == 12
    assert plan["resolution_in_global_prefix"] is False
    assert plan["closure_eligible"] is False
    assert "resolution_after_eligible_global_prefix" in plan["closure_blockers"]
    assert plan["incomplete_tail_turns"] == 1


def test_only_global_updates_advance_the_incorporated_prefix() -> None:
    short = batch_plan(
        raw_turns=8,
        intermediate_limit=2,
        global_updates=3,
        batch_size=4,
        available_turns=28,
        resolution_turn=18,
    )
    assert short["global_prefix_turns"] == 12
    assert short["resolution_in_global_prefix"] is False
    assert short["closure_eligible"] is False

    partial = batch_plan(
        raw_turns=8,
        intermediate_limit=2,
        global_updates=9,
        batch_size=4,
        available_turns=37,
        resolution_turn=34,
    )
    assert partial["global_prefix_turns"] == 20
    assert partial["resolution_in_global_prefix"] is False
    assert partial["sufficient"] is False

    long = batch_plan(
        raw_turns=8,
        intermediate_limit=2,
        global_updates=9,
        batch_size=4,
        available_turns=52,
        resolution_turn=34,
    )
    assert long["required_turns"] == 52
    assert long["global_prefix_turns"] == 36
    assert long["resolution_in_global_prefix"] is True
    assert long["closure_eligible"] is True


@pytest.mark.parametrize(
    "values",
    [
        (True, 0, 0, 4, 40, 34),
        (-1, 0, 0, 4, 40, 34),
        (0, 0, 0, 0, 40, 34),
    ],
)
def test_batch_plan_rejects_invalid_inputs(values: tuple[int, int, int, int, int, int]) -> None:
    with pytest.raises(ValueError):
        batch_plan(
            raw_turns=values[0],
            intermediate_limit=values[1],
            global_updates=values[2],
            batch_size=values[3],
            available_turns=values[4],
            resolution_turn=values[5],
        )


def test_builder_uses_real_handlers_and_emits_annotated_complete_batches(tmp_path: Path) -> None:
    result = build_scenario(batch_size=5)

    assert len(result.sources.turns) >= 52
    assert any(
        op.payload.name == "update_quest"
        for t in result.sources.turns
        for op in t.operations or ()
    )
    assert any(
        op.payload.name == "invoke_npc" for t in result.sources.turns for op in t.operations or ()
    )
    assert result.annotations["synthetic"] is True
    assert result.annotations["chapters"]
    assert all(turn.operations is not None for turn in result.sources.turns)
    operations = [op for turn in result.sources.turns for op in turn.operations or ()]
    dice = next(op for op in operations if op.payload.name == "request_dice")
    assert dice.payload.outcome == "succeeded" and not dice.payload.deltas
    npc_ops = [op for op in operations if op.payload.name == "invoke_npc"]
    assert sum(op.payload.result.status == "speaking" for op in npc_ops) == 1
    assert any(op.payload.result.status == "silent" and not op.payload.deltas for op in npc_ops)
    fulfilment = next(op for op in npc_ops if op.payload.result.status == "speaking")
    assert fulfilment.payload.result.kind == "npc"
    trust_delta = next(
        delta
        for turn in result.sources.turns
        for operation in turn.operations or ()
        if operation.payload.name == "change_npc_psychology"
        for delta in operation.payload.deltas
        if delta.path[-1] == "trust"
    )
    assert trust_delta.after.presence == "present"
    assert trust_delta.after.value - trust_delta.before.value == 8  # type: ignore[union-attr]
    assert (
        "The original was kept beneath the ferry ledger."
        in result.sources.turns[result.annotations["anchors"]["resolution_turn"] - 1].narration
    )
    assert result.annotations["quest_status_chronology"] == [
        "active",
        "completed",
        "active",
        "completed",
    ]
    anchors = result.annotations["anchors"]
    assert anchors["promise_turn"] == 1 and anchors["belief_turn"] == 2
    assert anchors["key_recovery_turn"] == 33
    assert anchors["resolution_turn"] == 34
    assert anchors["resolution_turn"] < len(result.sources.turns)
    belief = result.sources.turns[anchors["belief_turn"] - 1]
    assert "Fixture Adventurer" in belief.player_action
    assert "Fixture Adventurer" in belief.narration
    promise = result.sources.turns[anchors["promise_turn"] - 1]
    assert anchors["resolution_npc"] in promise.player_action
    resolution = result.sources.turns[anchors["resolution_turn"] - 1]
    assert anchors["resolution_npc"] in resolution.narration
    assert result.annotations["expected_threads"]["sealed_key"]["before_resolution"] == "open"
    assert result.annotations["expected_threads"]["sealed_key"]["after_resolution"] == "closed"
    assert (
        sum(
            "The original was kept beneath the ferry ledger." in turn.narration
            for turn in result.sources.turns
        )
        == 1
    )

    out = tmp_path / "result"
    write_scenario(result, out)
    batch_files = sorted((out / "batches").glob("*.json"))
    assert batch_files
    serialized = [json.loads(path.read_text()) for path in batch_files]
    cli_batches = json.loads((out / "batches.json").read_text())
    assert isinstance(cli_batches, list)
    roundtripped = [BatchInput.model_validate_json(json.dumps(batch)) for batch in cli_batches]
    assert tuple(roundtripped) == result.batches
    complete_count = sum(len(batch["turns"]) for batch in serialized)
    tail_path = out / "incomplete-tail.json"
    tail_count = len(json.loads(tail_path.read_text())["turns"]) if tail_path.exists() else 0
    assert complete_count + tail_count == len(result.sources.turns)
    assert all(len(batch["turns"]) == 5 for batch in serialized)
    resolution_id = result.sources.turns[anchors["resolution_turn"] - 1].turn_id
    resolution_batch = next(
        batch for batch in roundtripped if resolution_id in {t.turn_id for t in batch.turns}
    )
    assert len(resolution_batch.turns) == 5
    assert tail_path.exists() and resolution_id not in {turn.turn_id for turn in result.tail.turns}
    assert all(
        turn["reference"] == f"t{index}"
        for batch in serialized
        for index, turn in enumerate(batch["turns"], start=1)
    )
    if tail_path.exists():
        assert all(
            turn["reference"] == f"t{index}"
            for index, turn in enumerate(json.loads(tail_path.read_text())["turns"], start=1)
        )
    try:
        write_scenario(result, out)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing output was not protected")


def test_builder_has_deterministic_ids_and_reports_partial_tail() -> None:
    first = build_scenario(batch_size=5)
    second = build_scenario(batch_size=5)

    assert first.sources.source_hash() == second.sources.source_hash()
    report = batch_plan(
        raw_turns=1,
        intermediate_limit=0,
        global_updates=0,
        batch_size=5,
        available_turns=len(first.sources.turns),
        resolution_turn=34,
    )
    assert report["incomplete_tail_turns"] == len(first.sources.turns) % 5


def test_only_test_plan_can_cover_the_resolution_in_long_source() -> None:
    # Test-only arithmetic inputs; this does not adopt an S3 production matrix.
    result = build_scenario(batch_size=4, plan=(8, 2, 9))

    assert len(result.sources.turns) == 52
    assert result.plan["global_prefix_turns"] == 36
    assert result.plan["resolution_turn"] == 34
    assert result.plan["closure_eligible"] is True
    assert result.annotations["expected_threads"]["sealed_key"]["after_resolution"] == "closed"
    assert result.annotations["expected_threads"]["ferry_manifest"]["after_resolution"] == "open"
    resolution_id = result.sources.turns[result.plan["resolution_turn"] - 1].turn_id
    resolution_batch = next(
        batch
        for batch in result.batches
        if resolution_id in {turn.turn_id for turn in batch.turns}
    )
    assert len(resolution_batch.turns) == 4
    ferry_updates = [
        operation
        for turn in result.sources.turns
        for operation in turn.operations or ()
        if operation.payload.name == "update_quest"
        and operation.payload.arguments.get("quest_id") == "ferry_manifest"
    ]
    assert len(ferry_updates) >= 4
    resolution_turn = result.sources.turns[result.plan["resolution_turn"] - 1]
    resolution_update = next(
        operation
        for operation in resolution_turn.operations or ()
        if operation.payload.name == "update_quest"
    )
    completed = next(
        delta for delta in resolution_update.payload.deltas if delta.path == ("completed",)
    )
    assert any(quest["id"] == "sealed_key" for quest in completed.after.value)
    final_active = next(
        delta for delta in ferry_updates[-1].payload.deltas if delta.path == ("active",)
    )
    assert any(quest["id"] == "ferry_manifest" for quest in final_active.after.value)
