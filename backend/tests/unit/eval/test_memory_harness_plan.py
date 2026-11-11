import json

import pytest
from eval.memory.plan import (
    MemoryPlan,
    load_plan,
    load_saved_plan,
    plan_seal,
    prepare_plan,
    validate_plan,
    write_plan,
)


def test_integrated_plan_is_non_executable_draft_with_offline_budget() -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan

    source = fixture_source()
    source["turns"] = [
        {
            "reference": f"t{index}",
            "turn_id": f"00000000-0000-0000-0000-{index:012d}",
            "player_action": "Act",
            "narration": "Result",
            "operations": None,
        }
        for index in range(1, 13)
    ]
    plan = prepare_integrated_plan(sources=source, run_id="offline-test")
    assert plan.approved is False
    assert plan.executable is False
    assert plan.sources.turns[0].reference == "t1"
    assert plan.batch_count == 1
    assert plan.global_count == 0
    assert plan.generation_baseline == 2
    assert plan.embedding_text_upper_bound == 6
    assert plan.missing_gates


def test_integrated_plan_budget_is_per_model_and_keeps_texts_distinct_from_attempts() -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan

    source = fixture_source()
    source["turns"] = [
        {
            "reference": f"t{index}",
            "turn_id": f"00000000-0000-0000-0000-{index:012d}",
            "player_action": "Act",
            "narration": "Result",
            "operations": None,
        }
        for index in range(1, 53)
    ]
    plan = prepare_integrated_plan(
        sources=source,
        run_id="source-52",
        generation_model="nvidia/nemotron-3.5-super-vl:free",
    )
    assert (plan.batch_count, plan.global_count) == (11, 9)
    assert plan.generation_baseline == 31
    assert plan.generation_with_sidecar == 42
    assert plan.generation_call_counts_by_model == {"nvidia/nemotron-3.5-super-vl:free": 31}
    assert plan.embedding_text_upper_bound == 66
    assert plan.failure_policy == "stop_before_job_retry"


def integrated_source(turn_count: int = 52) -> dict[str, object]:
    source = fixture_source()
    source["turns"] = [
        {
            "reference": f"t{index}",
            "turn_id": f"00000000-0000-0000-0000-{index:012d}",
            "player_action": "Act",
            "narration": "Result",
            "operations": None,
        }
        for index in range(1, turn_count + 1)
    ]
    return source


def test_integrated_plan_snapshots_generation_output_cap_and_requires_paid_allowance() -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan

    from app.ai.router import get_instance_default

    plan = prepare_integrated_plan(
        sources=integrated_source(), run_id="caps", generation_model="vendor/model"
    )
    assert plan.output_cap == get_instance_default().max_tokens
    assert plan.allow_paid_generation is False
    assert "paid_generation_allowance" in plan.missing_gates


@pytest.mark.parametrize(
    ("field", "value"),
    [("run_id", " "), ("generation_model", " "), ("language", " ")],
)
def test_integrated_plan_rejects_whitespace_selectors(field: str, value: str) -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan

    kwargs = {"run_id": "valid", field: value}
    with pytest.raises(ValueError, match="empty"):
        prepare_integrated_plan(sources=integrated_source(), **kwargs)


def test_integrated_write_rejects_orphan_evidence_files(tmp_path) -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan
    from eval.integrated_memory.plan import write_plan as write_integrated_plan

    plan = prepare_integrated_plan(sources=integrated_source(), run_id="orphan")
    (tmp_path / "requests.jsonl").write_text("")
    with pytest.raises(ValueError, match="evidence artifacts"):
        write_integrated_plan(plan, tmp_path)


def test_integrated_saved_manifest_revalidates_source_structure(tmp_path) -> None:
    from eval.integrated_memory.plan import IntegratedPlan, _plan_seal
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan
    from eval.integrated_memory.plan import write_plan as write_integrated_plan

    plan = prepare_integrated_plan(sources=integrated_source(), run_id="tampered-refs")
    write_integrated_plan(plan, tmp_path)
    path = tmp_path / "manifest.json"
    value = json.loads(path.read_text())
    value["sources"]["turns"][0]["reference"] = "t2"
    value["seal"] = ""
    altered = IntegratedPlan.model_validate_json(json.dumps(value))
    value["source_hash"] = altered.sources.source_hash()
    altered = IntegratedPlan.model_validate_json(json.dumps(value))
    value["seal"] = _plan_seal(altered)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="references"):
        from eval.integrated_memory.plan import load_plan as load_integrated_plan

        load_integrated_plan(tmp_path)


def test_integrated_fingerprint_includes_root_config(monkeypatch) -> None:
    from pathlib import Path

    from eval.integrated_memory.plan import _fingerprint

    root = Path(__file__).resolve().parents[3]
    original = _fingerprint(root)
    read_bytes = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: (
            read_bytes(path) + b"\n" if path.name == "saga.config.yaml" else read_bytes(path)
        ),
    )
    assert _fingerprint(root) != original


def fixture_source() -> dict[str, object]:
    return {
        "turns": [
            {
                "reference": "t1",
                "turn_id": "00000000-0000-0000-0000-000000000001",
                "player_action": "Ask",
                "narration": "A door opens.",
                "operations": None,
            },
            {
                "reference": "t2",
                "turn_id": "00000000-0000-0000-0000-000000000002",
                "player_action": "Wait",
                "narration": "The party rests.",
                "operations": None,
            },
        ]
    }


def policy() -> dict[str, object]:
    return {
        "max_per_batch": 2,
        "importance_levels": [{"name": "high", "criteria": "Major", "examples": "A secret"}],
    }


def test_prepare_plan_freezes_sources_and_calculates_budget(tmp_path) -> None:
    plan = prepare_plan(
        sources=[fixture_source(), fixture_source()],
        facts_policy=policy(),
        global_policy={"target_words": 120},
        language="en",
        models=["provider/model"],
        repetitions=2,
        global_count=1,
        session_scope="adr-0020-memory-s3",
    )
    assert plan.call_budget == 2 * (3 * 2 + 1)
    assert plan.producer_version == "memory-v1"
    assert len(plan.implementation_fingerprint) == 64
    assert plan.output_cap > 0
    write_plan(plan, tmp_path)
    assert MemoryPlan.model_validate_json((tmp_path / "manifest.json").read_text()) == plan


def test_manifest_rejects_source_or_setting_edits(tmp_path) -> None:
    original = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="adr-0020-memory-s3",
    )
    write_plan(original, tmp_path)
    changed = fixture_source()
    changed["turns"][0]["narration"] = "A different door opens."
    edited = prepare_plan(
        sources=[changed],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="adr-0020-memory-s3",
    )
    with pytest.raises(ValueError, match="manifest"):
        write_plan(edited, tmp_path)


def test_global_count_cannot_exceed_available_batches() -> None:
    with pytest.raises(ValueError, match="global_count"):
        prepare_plan(
            sources=[fixture_source()],
            facts_policy=policy(),
            global_policy={"target_words": 120},
            language="en",
            models=["provider/model"],
            repetitions=1,
            global_count=2,
            session_scope="adr-0020-memory-s3",
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("models", ["provider/edited"]),
        ("repetitions", 2),
        ("global_count", 1),
        ("language", "it"),
        (
            "facts_policy",
            {
                "max_per_batch": 1,
                "importance_levels": [
                    {"name": "high", "criteria": "Major", "examples": "A secret"}
                ],
            },
        ),
    ],
)
def test_manifest_seal_rejects_non_source_edits(tmp_path, field, replacement) -> None:
    plan = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="adr-0020-memory-s3",
    )
    write_plan(plan, tmp_path)
    path = tmp_path / "manifest.json"
    changed = json.loads(path.read_text())
    changed[field] = replacement
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="seal"):
        load_plan(tmp_path)


def test_manifest_rejects_changed_instruction_fingerprint(tmp_path, monkeypatch) -> None:
    import eval.memory.plan as plan_module

    plan = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="adr-0020-memory-s3",
    )
    write_plan(plan, tmp_path)
    monkeypatch.setattr(plan_module, "current_implementation_fingerprint", lambda: "changed")
    with pytest.raises(ValueError, match="instructions changed"):
        load_plan(tmp_path)


def test_fingerprint_includes_the_complete_memory_harness(monkeypatch) -> None:
    from pathlib import Path

    from eval.memory.plan import current_implementation_fingerprint

    original = current_implementation_fingerprint()
    read_bytes = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: read_bytes(path) + b"\n" if path.name == "report.py" else read_bytes(path),
    )
    assert current_implementation_fingerprint() != original


@pytest.mark.parametrize("filename", ["dialogue_affinity.py", "limits.py"])
def test_fingerprint_includes_shared_session_and_quota_helpers(monkeypatch, filename) -> None:
    from pathlib import Path

    from eval.memory.plan import current_implementation_fingerprint

    original = current_implementation_fingerprint()
    read_bytes = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: read_bytes(path) + b"\n" if path.name == filename else read_bytes(path),
    )
    assert current_implementation_fingerprint() != original


def test_model_session_id_is_scoped_only_by_scope_and_model() -> None:
    first = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model", "other/model"],
        repetitions=1,
        global_count=0,
        session_scope="scope-a",
    )
    second = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=3,
        global_count=0,
        session_scope="scope-a",
    )
    assert first.model_session_id("provider/model") == second.model_session_id("provider/model")
    assert first.model_session_id("provider/model") != first.model_session_id("other/model")
    with pytest.raises(ValueError, match="selected"):
        first.model_session_id("missing/model")
    other_scope = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="scope-b",
    )
    assert first.model_session_id("provider/model") != other_scope.model_session_id(
        "provider/model"
    )


def test_version_one_manifest_keeps_original_seal_and_is_not_executable(
    tmp_path, monkeypatch
) -> None:
    import eval.memory.plan as plan_module

    current = prepare_plan(
        sources=[fixture_source()],
        facts_policy=policy(),
        global_policy=None,
        language="en",
        models=["provider/model"],
        repetitions=1,
        global_count=0,
        session_scope="temporary",
    )
    legacy = current.model_dump(mode="json")
    legacy["version"] = 1
    legacy["harness_version"] = "1"
    legacy.pop("session_scope")
    legacy_plan = MemoryPlan.model_validate_json(json.dumps(legacy))
    legacy["seal"] = plan_seal(legacy_plan)
    (tmp_path / "manifest.json").write_text(json.dumps(legacy))
    assert load_saved_plan(tmp_path).version == 1
    monkeypatch.setattr(
        plan_module,
        "current_implementation_fingerprint",
        lambda: pytest.fail("legacy execution must reject before fingerprint lookup"),
    )
    with pytest.raises(ValueError, match="cannot be executed"):
        validate_plan(load_saved_plan(tmp_path))
