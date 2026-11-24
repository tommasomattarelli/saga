import json

import pytest

from tests.unit.eval._integrated_sources import integrated_source


def test_integrated_plan_is_non_executable_draft_with_offline_budget() -> None:
    from eval.integrated_memory.plan import prepare_plan as prepare_integrated_plan

    plan = prepare_integrated_plan(sources=integrated_source(12), run_id="offline-test")
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

    plan = prepare_integrated_plan(
        sources=integrated_source(),
        run_id="source-52",
        generation_model="nvidia/nemotron-3.5-super-vl:free",
    )
    assert (plan.batch_count, plan.global_count) == (11, 9)
    assert plan.generation_baseline == 31
    assert plan.generation_with_sidecar == 42
    assert plan.generation_call_counts_by_model == {"nvidia/nemotron-3.5-super-vl:free": 31}
    assert plan.embedding_text_upper_bound == 66
    assert plan.failure_policy == "stop_before_job_retry"


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
